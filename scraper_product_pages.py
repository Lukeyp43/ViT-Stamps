from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import re
import time
import json
from typing import List, Dict, Optional, Set
import sqlite3


class StampProductScraper:
    def __init__(self, db_path: str = "stamps.db", headless: bool = True):
        self.start_url = "https://www.mysticstamp.com/1-1854-western-australia/"
        self.db_path = db_path
        self.scraped_ids: Set[str] = set()
        self.headless = headless
        self.driver = None
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

    def init_driver(self):
        """Initialize Selenium WebDriver"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        self.driver = webdriver.Chrome(options=chrome_options)

    def close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()

    def is_valid_stamp_number(self, number_text: str) -> bool:
        """Check if stamp number contains only digits (no ranges, slashes, etc)"""
        # Remove # if present
        number_text = number_text.replace('#', '').strip()

        # Check if it's just digits (single number)
        return number_text.isdigit()

    def extract_product_data(self) -> Optional[Dict]:
        """Extract data from current product page"""
        try:
            # Get product ID from the productView-nextProducts div
            try:
                next_products_div = self.driver.find_element(By.CSS_SELECTOR, 'div.productView-nextProducts')
                product_id = next_products_div.get_attribute('data-product-id')
            except:
                product_id = None

            # Skip if already scraped
            if product_id and product_id in self.scraped_ids:
                return None

            # Extract image URL
            try:
                # Try to find the zoomImg image first
                img_element = self.driver.find_element(By.CSS_SELECTOR, 'img.zoomImg')
                image_url = img_element.get_attribute('src')

                # If not found or empty, try data-zoombaimage attribute
                if not image_url:
                    image_url = img_element.get_attribute('data-zoombaimage')
            except:
                # Fallback to regular product image
                try:
                    img_element = self.driver.find_element(By.CSS_SELECTOR, 'img[role="presentation"]')
                    image_url = img_element.get_attribute('src')
                    if not image_url:
                        image_url = img_element.get_attribute('data-zoombaimage')
                except:
                    return None

            # Skip if image is "coming soon" placeholder
            if not image_url or 'new-image-coming-soon.jpg' in image_url:
                return None

            # Extract title (year + country)
            try:
                title_element = self.driver.find_element(By.CSS_SELECTOR, 'h1.productView-title')
                title_text = title_element.text.strip()
            except:
                return None

            if not title_text:
                return None

            # Extract year (first 4 digits)
            year_match = re.match(r'(\d{4})', title_text)
            if not year_match:
                return None
            year = year_match.group(1)

            # Extract country (text after year and space)
            country = title_text[4:].strip()
            if not country:
                return None

            # Extract stamp number from h6 title
            try:
                stamp_number_element = self.driver.find_element(By.CSS_SELECTOR, 'h6.productView-title')
                stamp_number_raw = stamp_number_element.text.strip()
            except:
                return None

            if not stamp_number_raw:
                return None

            # Validate stamp number (must be single number only)
            if not self.is_valid_stamp_number(stamp_number_raw):
                return None

            # Create full stamp number: Country + number (e.g., "Norway 1")
            stamp_number = f"{country} {stamp_number_raw.replace('#', '').strip()}"

            # Extract price
            try:
                price_element = self.driver.find_element(By.CSS_SELECTOR, 'span.price--withoutTax')
                price_text = price_element.text.strip()

                # Extract numeric value from price
                price_match = re.search(r'\$([\d,]+\.?\d*)', price_text)
                if not price_match:
                    return None
                price = float(price_match.group(1).replace(',', ''))
            except:
                return None

            # Mark this product as scraped
            if product_id:
                self.scraped_ids.add(product_id)

            return {
                'product_id': product_id or f"{country}_{stamp_number_raw.replace('#', '').strip()}",
                'image_url': image_url,
                'stamp_number': stamp_number,
                'year': year,
                'country': country,
                'price': price
            }

        except Exception as e:
            print(f"Error extracting product data: {e}")
            return None

    def click_next_button(self) -> bool:
        """Click the Next button to go to next product. Returns True if successful."""
        try:
            # Find the Next button
            next_button = self.driver.find_element(By.CSS_SELECTOR, 'a.next-icon-new')

            # Check if it's disabled or not visible
            if 'disable' in next_button.get_attribute('class'):
                return False

            # Get the href before clicking
            next_url = next_button.get_attribute('href')
            if not next_url or next_url == '#':
                return False

            # Click the button
            next_button.click()

            # Wait for page to load
            time.sleep(2)

            return True

        except Exception as e:
            print(f"Error clicking next button: {e}")
            return False

    def save_to_database(self, stamp: Dict):
        """Save single stamp to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

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
            conn.commit()
        except sqlite3.IntegrityError:
            pass

        conn.close()

    def save_to_json_incremental(self, stamp: Dict, json_file: str = "stamps.json"):
        """Append single stamp to JSON file incrementally"""
        # Read existing data
        try:
            with open(json_file, 'r') as f:
                existing_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing_data = []

        # Append new stamp
        existing_data.append(stamp)

        # Write back to file
        with open(json_file, 'w') as f:
            json.dump(existing_data, f, indent=2)

    def scrape_all(self, delay: float = 2.0, max_products: Optional[int] = None):
        """
        Scrape all products by clicking through Next buttons

        Args:
            delay: Delay between requests in seconds
            max_products: Maximum number of products to scrape (None for unlimited)
        """
        self.init_driver()

        try:
            # Navigate to starting URL
            print(f"Starting at: {self.start_url}")
            self.driver.get(self.start_url)
            time.sleep(3)

            product_count = 0
            skipped_count = 0
            total_scraped = 0

            while True:
                if max_products and total_scraped >= max_products:
                    print(f"Reached maximum product limit: {max_products}")
                    break

                product_count += 1
                print(f"\nProcessing product #{product_count}...")

                # Extract data from current page
                stamp_data = self.extract_product_data()

                if stamp_data:
                    print(f"  ✓ Scraped: {stamp_data['stamp_number']} - ${stamp_data['price']}")
                    self.save_to_database(stamp_data)
                    self.save_to_json_incremental(stamp_data)
                    total_scraped += 1
                    print(f"  → Total scraped: {total_scraped}")
                else:
                    skipped_count += 1
                    print(f"  ✗ Skipped (invalid or duplicate)")

                # Click Next button
                if not self.click_next_button():
                    print("\nNo more products (Next button disabled or not found)")
                    break

                # Delay between requests
                time.sleep(delay)

            print(f"\n{'='*60}")
            print(f"Scraping complete!")
            print(f"Total products processed: {product_count}")
            print(f"Total scraped: {total_scraped}")
            print(f"Total skipped: {skipped_count}")
            print(f"Database location: {self.db_path}")
            print(f"{'='*60}")

        finally:
            self.close_driver()

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
    # Initialize scraper (headless=False to see browser window)
    scraper = StampProductScraper(db_path="stamps.db", headless=True)

    # Scrape all products with 2 second delay between requests
    scraper.scrape_all(delay=2.0)
