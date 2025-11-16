import requests
import re
import json
import sqlite3
from typing import List, Dict, Optional, Set
import time


class StampAPIScraper:
    def __init__(self, db_path: str = "stamps.db"):
        self.api_url = "https://zyfff9.a.searchspring.io/api/search/search.json"
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
        parts = stamp_number_text.strip().split()
        if not parts:
            return False

        # The last part should be the number
        number_part = parts[-1]

        # Check if it's just digits (single number)
        return number_part.isdigit()

    def extract_stamp_data(self, result: Dict) -> Optional[Dict]:
        """Extract data from a single API result"""
        try:
            # Get product ID (use uid field)
            product_id = str(result.get('uid', '') or result.get('id', ''))
            if not product_id or product_id in self.scraped_ids:
                return None

            # Extract image URL
            image_url = result.get('imageUrl', '') or result.get('thumbnailImageUrl', '')
            if not image_url or 'new-image-coming-soon.jpg' in image_url:
                return None

            # Extract stamp number from SKU field (e.g., "Norway 1")
            stamp_number_text = result.get('sku', '')
            if not stamp_number_text:
                return None

            # Validate stamp number (must be single number only)
            if not self.is_valid_stamp_number(stamp_number_text):
                return None

            # Extract title (contains year + country, e.g., "1 - 1855 Norway")
            title = result.get('name', '')
            if not title:
                return None

            # Parse title - format is "number - year country"
            # Example: "1 - 1855 Norway"
            parts = title.split(' - ')
            if len(parts) < 2:
                return None

            year_country = parts[1].strip()

            # Extract year (first 4 digits)
            year_match = re.match(r'(\d{4})', year_country)
            if not year_match:
                return None
            year = year_match.group(1)

            # Extract country (text after year and space)
            country = year_country[4:].strip()
            if not country:
                return None

            # Extract price
            price = result.get('price') or result.get('ss_price')
            if price is None:
                return None

            try:
                price = float(price)
            except (ValueError, TypeError):
                return None

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
            print(f"  Error extracting stamp data: {e}")
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
                continue

        conn.commit()
        conn.close()

    def save_to_json_incremental(self, stamps: List[Dict], json_file: str = "stamps.json"):
        """Append new stamps to JSON file incrementally"""
        if not stamps:
            return

        # Read existing data
        try:
            with open(json_file, 'r') as f:
                existing_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing_data = []

        # Append new stamps
        existing_data.extend(stamps)

        # Write back to file
        with open(json_file, 'w') as f:
            json.dump(existing_data, f, indent=2)

        print(f"  → Saved to {json_file} (total: {len(existing_data)} stamps)")

    def scrape_page(self, page_num: int) -> List[Dict]:
        """Scrape a single page via API"""
        params = {
            'siteId': 'zyfff9',
            'page': page_num,
            'bgfilter.categories_hierarchy': 'Worldwide',
            'bgfilter.ss_ad': '0',
            'redirectResponse': 'full',
            'resultsFormat': 'native',
            'resultsPerPage': 96  # Get 96 items per page instead of 32
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': '*/*',
            'Referer': 'https://www.mysticstamp.com/'
        }

        try:
            print(f"Fetching page {page_num} from API...")
            response = requests.get(self.api_url, params=params, headers=headers, timeout=30)

            # Check for rate limiting
            if response.status_code == 429:
                print(f"  Rate limited! Waiting 30 seconds...")
                time.sleep(30)
                # Retry once
                response = requests.get(self.api_url, params=params, headers=headers, timeout=30)

            response.raise_for_status()

            data = response.json()

            # Extract results
            results = data.get('results', [])
            print(f"  Found {len(results)} items in API response")

            stamps = []
            for result in results:
                stamp_data = self.extract_stamp_data(result)
                if stamp_data:
                    stamps.append(stamp_data)

            return stamps

        except Exception as e:
            print(f"  Error fetching page {page_num}: {e}")
            return []

    def scrape_all(self, delay: float = 1.0, max_pages: Optional[int] = None):
        """
        Scrape all pages via API

        Args:
            delay: Delay between API requests in seconds
            max_pages: Maximum number of pages to scrape (None for unlimited)
        """
        page_num = 1
        total_scraped = 0
        consecutive_empty = 0

        print("Starting API scraping...")
        print("="*60)

        while True:
            if max_pages and page_num > max_pages:
                print(f"\nReached maximum page limit: {max_pages}")
                break

            print(f"\n--- Page {page_num} ---")
            stamps = self.scrape_page(page_num)

            if stamps:
                print(f"  ✓ Found {len(stamps)} valid stamps")
                self.save_to_database(stamps)
                self.save_to_json_incremental(stamps)
                total_scraped += len(stamps)
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                print(f"  ✗ No new valid stamps")

            # Stop if 3 consecutive empty pages
            if consecutive_empty >= 3:
                print("\nNo new data in last 3 pages. Stopping.")
                break

            page_num += 1
            time.sleep(delay)

        print(f"\n{'='*60}")
        print(f"Scraping complete!")
        print(f"Total pages scraped: {page_num - 1}")
        print(f"Total stamps scraped: {total_scraped}")
        print(f"Database location: {self.db_path}")
        print(f"{'='*60}")

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
    scraper = StampAPIScraper(db_path="stamps.db")

    # Scrape all pages with 1 second delay to avoid rate limiting
    scraper.scrape_all(delay=1.0)

    # Export to JSON
    scraper.export_to_json("stamps.json")
