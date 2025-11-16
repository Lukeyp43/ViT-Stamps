import requests
import re
import time
import json
from typing import List, Dict, Optional, Set
import sqlite3


class StampAPICategoryScraper:
    """Scrape stamps by category to bypass pagination limits"""

    def __init__(self, db_path: str = "stamps.db"):
        self.api_url = "https://zyfff9.a.searchspring.io/api/search/search.json"
        self.db_path = db_path
        self.scraped_ids: Set[str] = set()

        # Define all categories under Worldwide
        self.categories = [
            "Worldwide>Africa",
            "Worldwide>Asia",
            "Worldwide>Australia & Oceania",
            "Worldwide>British Colonies",
            "Worldwide>Canada",
            "Worldwide>Caribbean",
            "Worldwide>Europe",
            "Worldwide>Germany",
            "Worldwide>Great Britain",
            "Worldwide>Latin America",
            "Worldwide>Middle East",
            "Worldwide>Stamp Packets by Country",
            "Worldwide>Topical Stamps",
            "Worldwide>Unique Country Collections",
            "Worldwide>United Nations"
        ]

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
                category TEXT,
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

        number_part = parts[-1]
        return number_part.isdigit()

    def extract_stamp_data(self, result: Dict, category: str) -> Optional[Dict]:
        """Extract data from a single API result"""
        try:
            product_id = str(result.get('uid', '') or result.get('id', ''))
            if not product_id or product_id in self.scraped_ids:
                return None

            image_url = result.get('imageUrl', '') or result.get('thumbnailImageUrl', '')
            if not image_url or 'new-image-coming-soon.jpg' in image_url:
                return None

            stamp_number_text = result.get('sku', '')
            if not stamp_number_text:
                return None

            if not self.is_valid_stamp_number(stamp_number_text):
                return None

            title = result.get('name', '')
            if not title or ' - ' not in title:
                return None

            parts = title.split(' - ', 1)
            if len(parts) < 2:
                return None

            year_country = parts[1].strip()

            year_match = re.match(r'(\d{4})', year_country)
            if not year_match:
                return None
            year = year_match.group(1)

            country = year_country[4:].strip()
            if not country:
                return None

            price = result.get('price')
            if price is None:
                return None
            price = float(price)

            self.scraped_ids.add(product_id)

            return {
                'product_id': product_id,
                'image_url': image_url,
                'stamp_number': stamp_number_text,
                'year': year,
                'country': country,
                'price': price,
                'category': category
            }

        except Exception as e:
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
                    (product_id, image_url, stamp_number, year, country, price, category)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stamp['product_id'],
                    stamp['image_url'],
                    stamp['stamp_number'],
                    stamp['year'],
                    stamp['country'],
                    stamp['price'],
                    stamp['category']
                ))
            except sqlite3.IntegrityError:
                continue

        conn.commit()
        conn.close()

    def save_to_json_incremental(self, stamps: List[Dict], json_file: str = "stamps.json"):
        """Append new stamps to JSON file incrementally"""
        if not stamps:
            return

        try:
            with open(json_file, 'r') as f:
                existing_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing_data = []

        existing_data.extend(stamps)

        with open(json_file, 'w') as f:
            json.dump(existing_data, f, indent=2)

    def scrape_category(self, category: str, delay: float = 1.0) -> int:
        """
        Scrape all stamps in a specific category

        Args:
            category: Category filter (e.g., "Worldwide>Africa")
            delay: Delay between requests in seconds

        Returns:
            Number of valid stamps scraped
        """
        page = 1
        total_scraped = 0
        consecutive_empty = 0

        print(f"\n{'='*60}")
        print(f"Scraping category: {category}")
        print(f"{'='*60}")

        while True:
            try:
                # Build request parameters
                params = {
                    "siteId": "zyfff9",
                    "page": page,
                    "resultsPerPage": 96,
                    "filter.categories_hierarchy": category,
                    "bgfilter.categories_hierarchy": "Worldwide",
                    "bgfilter.ss_ad": "0",
                    "redirectResponse": "full",
                    "noBeacon": "true",
                    "ajaxCatalog": "Snap",
                    "resultsFormat": "native"
                }

                # Make API request
                response = requests.get(self.api_url, params=params)

                # Handle rate limiting
                if response.status_code == 429:
                    print(f"  Rate limited, waiting 30 seconds...")
                    time.sleep(30)
                    continue

                if response.status_code != 200:
                    print(f"  Error: Status {response.status_code}")
                    break

                data = response.json()
                results = data.get('results', [])

                if not results:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break
                    page += 1
                    time.sleep(delay)
                    continue

                consecutive_empty = 0

                # Extract stamps from results
                stamps = []
                for result in results:
                    stamp_data = self.extract_stamp_data(result, category)
                    if stamp_data:
                        stamps.append(stamp_data)

                if stamps:
                    print(f"  Page {page}: {len(stamps)} valid stamps")
                    self.save_to_database(stamps)
                    self.save_to_json_incremental(stamps)
                    total_scraped += len(stamps)

                # Check pagination
                pagination = data.get('pagination', {})
                current_page = pagination.get('currentPage', page)
                total_pages = pagination.get('totalPages', 0)

                print(f"  Progress: Page {current_page}/{total_pages}")

                if current_page >= total_pages:
                    break

                page += 1
                time.sleep(delay)

            except Exception as e:
                print(f"  Error on page {page}: {e}")
                time.sleep(delay)
                page += 1
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break

        print(f"\nCategory '{category}' complete: {total_scraped} stamps")
        return total_scraped

    def scrape_all_categories(self, delay: float = 1.0):
        """Scrape all stamps across all categories"""
        total_scraped = 0

        print("\n" + "="*60)
        print("Starting category-based scraping...")
        print(f"Total categories to process: {len(self.categories)}")
        print("="*60)

        for i, category in enumerate(self.categories, 1):
            print(f"\n[{i}/{len(self.categories)}] Processing: {category}")
            count = self.scrape_category(category, delay=delay)
            total_scraped += count

            # Delay between categories
            if i < len(self.categories):
                print(f"\nWaiting {delay} seconds before next category...")
                time.sleep(delay)

        print(f"\n{'='*60}")
        print(f"Scraping complete!")
        print(f"Total stamps scraped: {total_scraped}")
        print(f"Total unique stamps: {len(self.scraped_ids)}")
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
    scraper = StampAPICategoryScraper(db_path="stamps.db")

    # Scrape all categories
    scraper.scrape_all_categories(delay=1.0)

    # Export to JSON
    scraper.export_to_json("stamps.json")
