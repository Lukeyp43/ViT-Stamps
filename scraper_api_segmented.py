import requests
import re
import time
import json
from typing import List, Dict, Optional, Set
import sqlite3


class StampAPISegmentedScraper:
    """Scrape stamps by segmenting data by first letter to bypass pagination limits"""

    def __init__(self, db_path: str = "stamps.db"):
        self.api_url = "https://api.searchspring.net/api/search/search.json"
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
        # Extract just the number part (after country name)
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
            # Get product ID from uid field
            product_id = str(result.get('uid', '') or result.get('id', ''))
            if not product_id or product_id in self.scraped_ids:
                return None

            # Extract image URL
            image_url = result.get('imageUrl', '') or result.get('thumbnailImageUrl', '')
            if not image_url or 'new-image-coming-soon.jpg' in image_url:
                return None

            # Extract stamp number from SKU (e.g., "Norway 1")
            stamp_number_text = result.get('sku', '')
            if not stamp_number_text:
                return None

            # Validate stamp number (must be single number only)
            if not self.is_valid_stamp_number(stamp_number_text):
                return None

            # Parse title format: "number - year country" (e.g., "1 - 1855 Norway")
            title = result.get('name', '')
            if not title or ' - ' not in title:
                return None

            parts = title.split(' - ', 1)
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
            price = result.get('price')
            if price is None:
                return None
            price = float(price)

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

    def scrape_with_query(self, query: str = "", delay: float = 1.0) -> int:
        """
        Scrape all stamps matching a query string

        Args:
            query: Search query to filter results (empty for all)
            delay: Delay between requests in seconds

        Returns:
            Number of valid stamps scraped
        """
        page = 1
        total_scraped = 0
        consecutive_no_new = 0

        while True:
            try:
                # Build request payload
                payload = {
                    "siteId": "scfnwy",
                    "resultsFormat": "native",
                    "resultsPerPage": 96,
                    "page": page
                }

                if query:
                    payload["q"] = query

                # Make API request
                response = requests.post(
                    self.api_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                )

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
                    break

                # Extract stamps from results
                stamps = []
                for result in results:
                    stamp_data = self.extract_stamp_data(result)
                    if stamp_data:
                        stamps.append(stamp_data)

                if stamps:
                    print(f"  Page {page}: {len(stamps)} valid stamps")
                    self.save_to_database(stamps)
                    self.save_to_json_incremental(stamps)
                    total_scraped += len(stamps)
                    consecutive_no_new = 0
                else:
                    consecutive_no_new += 1

                # Stop if no new data for 3 pages
                if consecutive_no_new >= 3:
                    break

                # Check pagination
                pagination = data.get('pagination', {})
                current_page = pagination.get('currentPage', page)
                total_pages = pagination.get('totalPages', 0)

                if current_page >= total_pages:
                    break

                page += 1
                time.sleep(delay)

            except Exception as e:
                print(f"  Error on page {page}: {e}")
                break

        return total_scraped

    def scrape_all_segmented(self, delay: float = 1.0):
        """
        Scrape all stamps by segmenting alphabetically

        This bypasses the pagination limit by searching for stamps starting
        with each letter of the alphabet separately.
        """
        # Define segments (letters A-Z plus numbers 0-9)
        segments = [chr(i) for i in range(ord('A'), ord('Z') + 1)]
        segments.extend([str(i) for i in range(10)])

        total_scraped = 0

        print("Starting segmented scraping...")
        print(f"Total segments to process: {len(segments)}")
        print("="*60)

        for segment in segments:
            print(f"\nSegment: '{segment}'")
            count = self.scrape_with_query(query=segment, delay=delay)
            total_scraped += count
            print(f"  Total from segment '{segment}': {count}")

            # Delay between segments
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
    scraper = StampAPISegmentedScraper(db_path="stamps.db")

    # Scrape all stamps using segmented approach
    scraper.scrape_all_segmented(delay=1.0)

    # Export to JSON
    scraper.export_to_json("stamps.json")
