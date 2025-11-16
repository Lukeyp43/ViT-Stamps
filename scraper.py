import requests
from bs4 import BeautifulSoup
import re
import time
import json
from typing import List, Dict, Optional, Set
import sqlite3


class StampScraper:
    def __init__(self, db_path: str = "stamps.db"):
        self.base_url = "https://www.mysticstamp.com/foreign-stamps/?tab=products&productsPage={}"
        self.db_path = db_path
        self.scraped_ids: Set[str] = set()
        self.init_database()

    def init_database(self):
        """Initialize SQLite database with stamps table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stamps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE,
                image_url TEXT,
                stamp_number TEXT,
                year TEXT,
                country TEXT,
                price REAL,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def is_valid_stamp_number(self, stamp_number_text: str) -> bool:
        """Check if stamp number contains only a single number (no ranges, slashes, etc)"""
        # Extract just the number part after the country name
        parts = stamp_number_text.strip().split()
        if not parts:
            return False

        # The last part should be the number
        number_part = parts[-1]

        # Check if it's just digits (single number)
        # Reject if it contains -, /, //, or other non-digit characters
        return number_part.isdigit()

    def extract_stamp_data(self, listing) -> Optional[Dict]:
        """Extract data from a single stamp listing"""
        try:
            # Get product ID to track duplicates
            product_id = listing.get('data-product-id')
            if not product_id or product_id in self.scraped_ids:
                return None

            # Extract image URL
            img_tag = listing.find('img', class_='card-image')
            if not img_tag:
                return None

            image_url = img_tag.get('src', '')

            # Skip if image is "coming soon" placeholder
            if 'new-image-coming-soon.jpg' in image_url:
                return None

            # Extract stamp number
            stamp_number_tag = listing.find('a', class_='StampNumber')
            if not stamp_number_tag:
                return None

            stamp_number_text = stamp_number_tag.get_text(strip=True)

            # Validate stamp number (must be single number only)
            if not self.is_valid_stamp_number(stamp_number_text):
                return None

            # Extract year and country
            title_tag = listing.find('a', class_='card-ellipsis')
            if not title_tag or not title_tag.find('span'):
                return None

            title_text = title_tag.find('span').get_text(strip=True)

            # Extract year (first 4 digits)
            year_match = re.match(r'(\d{4})', title_text)
            if not year_match:
                return None
            year = year_match.group(1)

            # Extract country (text after year and space)
            country = title_text[4:].strip()

            # Extract price
            price_tag = listing.find('span', class_='price--withoutTax')
            if not price_tag:
                return None

            price_text = price_tag.get_text(strip=True)
            # Extract numeric value from price (remove $ and convert to float)
            price_match = re.search(r'\$([\d,]+\.?\d*)', price_text)
            if not price_match:
                return None
            price = float(price_match.group(1).replace(',', ''))

            # Mark this product as scraped
            self.scraped_ids.add(product_id)

            return {
                'product_id': product_id,
                'image_url': image_url,
                'stamp_number': stamp_number_text,
                'year': year,
                'country': country,
                'price': price
            }

        except Exception as e:
            print(f"Error extracting stamp data: {e}")
            return None

    def save_to_database(self, stamps: List[Dict]):
        """Save scraped stamps to database"""
        if not stamps:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for stamp in stamps:
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO stamps
                    (product_id, image_url, stamp_number, year, country, price)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    stamp['product_id'],
                    stamp['image_url'],
                    stamp['stamp_number'],
                    stamp['year'],
                    stamp['country'],
                    stamp['price']
                ))
            except sqlite3.IntegrityError:
                # Skip duplicate entries
                continue

        conn.commit()
        conn.close()

    def scrape_page(self, page_num: int) -> List[Dict]:
        """Scrape a single page and return list of stamp data"""
        url = self.base_url.format(page_num) + "#/pageSize:96"
        print(f"Scraping page {page_num}...")

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find all stamp listings
            listings = soup.find_all('li', class_='ss__result')

            stamps = []
            for listing in listings:
                stamp_data = self.extract_stamp_data(listing)
                if stamp_data:
                    stamps.append(stamp_data)

            return stamps

        except Exception as e:
            print(f"Error scraping page {page_num}: {e}")
            return []

    def scrape_all(self, delay: float = 2.0, max_pages: Optional[int] = None):
        """
        Scrape all pages until no new data is found

        Args:
            delay: Delay between requests in seconds (be respectful to the server)
            max_pages: Maximum number of pages to scrape (None for unlimited)
        """
        page_num = 1
        consecutive_empty_pages = 0
        total_scraped = 0

        while True:
            if max_pages and page_num > max_pages:
                print(f"Reached maximum page limit: {max_pages}")
                break

            stamps = self.scrape_page(page_num)

            if stamps:
                print(f"Found {len(stamps)} valid stamps on page {page_num}")
                self.save_to_database(stamps)
                total_scraped += len(stamps)
                consecutive_empty_pages = 0
            else:
                consecutive_empty_pages += 1
                print(f"No new valid stamps found on page {page_num}")

            # Stop if we've had 3 consecutive pages with no new data
            if consecutive_empty_pages >= 3:
                print("No new data found in last 3 pages. Stopping.")
                break

            page_num += 1

            # Be respectful - delay between requests
            time.sleep(delay)

        print(f"\nScraping complete! Total stamps scraped: {total_scraped}")
        print(f"Database location: {self.db_path}")

    def export_to_json(self, output_file: str = "stamps.json"):
        """Export all stamps from database to JSON file"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM stamps')

        columns = [description[0] for description in cursor.description]
        stamps = []

        for row in cursor.fetchall():
            stamps.append(dict(zip(columns, row)))

        conn.close()

        with open(output_file, 'w') as f:
            json.dump(stamps, f, indent=2)

        print(f"Exported {len(stamps)} stamps to {output_file}")


if __name__ == "__main__":
    # Initialize scraper
    scraper = StampScraper(db_path="stamps.db")

    # Scrape all pages with 2 second delay between requests
    scraper.scrape_all(delay=2.0)

    # Optional: Export to JSON
    scraper.export_to_json("stamps.json")
