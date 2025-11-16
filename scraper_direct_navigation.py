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
        """Initialize Selenium WebDriver - opens browser and navigates to homepage"""
        chrome_options = Options()
        # Force non-headless so user can see and interact
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        self.driver = webdriver.Chrome(options=chrome_options)

        print("\n" + "="*60)
        print("Browser opened!")
        print("="*60)
        print("\nNavigating to https://www.mysticstamp.com/ ...")

        self.driver.get("https://www.mysticstamp.com/")
        time.sleep(3)

        print("\n" + "="*60)
        print("MANUAL STEPS:")
        print("="*60)
        print("1. Click on 'Worldwide' in the navigation menu")
        print("2. Navigate to the first product you want to scrape")
        print("   (e.g., click on a product or go to a specific product page)")
        print("\nOnce you're on the product page, press ENTER here to start scraping...")
        print("="*60)
        input("\nPress ENTER when ready: ")

    def close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()

    def is_valid_stamp_number(self, number_text: str) -> bool:
        """Check if stamp number contains only digits (no ranges, slashes, etc)"""
        number_text = number_text.replace('#', '').strip()
        return number_text.isdigit()

    def get_next_url(self) -> Optional[str]:
        """Extract next product URL from the current page"""
        try:
            next_button = self.driver.find_element(By.CSS_SELECTOR, 'a.next-icon-new')

            # Check if disabled
            button_class = next_button.get_attribute('class')
            if 'disable' in button_class:
                return None

            next_url = next_button.get_attribute('href')
            if not next_url or next_url == '#' or 'mysticstamp.com' not in next_url:
                return None

            return next_url
        except:
            return None

    def extract_product_data(self) -> Optional[Dict]:
        """Extract data from current product page"""
        try:
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'h1.productView-title'))
            )
            time.sleep(2)

            # Get product ID
            try:
                next_products_div = self.driver.find_element(By.CSS_SELECTOR, 'div.productView-nextProducts')
                product_id = next_products_div.get_attribute('data-product-id')
            except:
                product_id = None

            if product_id and product_id in self.scraped_ids:
                return None

            # Extract image - try multiple approaches
            image_url = None
            try:
                # Try finding product image
                imgs = self.driver.find_elements(By.TAG_NAME, 'img')
                for img in imgs:
                    src = img.get_attribute('src')
                    if src and 'products' in src and 'stencil' in src:
                        image_url = src
                        break
            except:
                pass

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

            # Extract country
            country = title_text[4:].strip()
            if not country:
                return None

            # Extract stamp number
            try:
                stamp_number_element = self.driver.find_element(By.CSS_SELECTOR, 'h6.productView-title')
                stamp_number_raw = stamp_number_element.text.strip()
            except:
                return None

            if not stamp_number_raw or not self.is_valid_stamp_number(stamp_number_raw):
                return None

            stamp_number = f"{country} {stamp_number_raw.replace('#', '').strip()}"

            # Extract price
            try:
                price_element = self.driver.find_element(By.CSS_SELECTOR, 'span.price--withoutTax')
                price_text = price_element.text.strip()
                price_match = re.search(r'\$([\d,]+\.?\d*)', price_text)
                if not price_match:
                    return None
                price = float(price_match.group(1).replace(',', ''))
            except:
                return None

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
            print(f"  Error extracting: {e}")
            return None

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
        """Append single stamp to JSON file"""
        try:
            with open(json_file, 'r') as f:
                existing_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing_data = []

        existing_data.append(stamp)

        with open(json_file, 'w') as f:
            json.dump(existing_data, f, indent=2)

    def scrape_all(self, delay: float = 2.0, max_products: Optional[int] = None):
        """Scrape all products from current page using Next button"""
        self.init_driver()

        try:
            product_count = 0
            skipped_count = 0
            total_scraped = 0

            print("\nStarting scraping from current page...")

            while True:
                if max_products and total_scraped >= max_products:
                    print(f"Reached maximum: {max_products}")
                    break

                product_count += 1
                current_url = self.driver.current_url
                print(f"\nProduct #{product_count}: {current_url}")

                # Extract data from current page
                stamp_data = self.extract_product_data()

                if stamp_data:
                    print(f"  ✓ {stamp_data['stamp_number']} - ${stamp_data['price']}")
                    self.save_to_database(stamp_data)
                    self.save_to_json_incremental(stamp_data)
                    total_scraped += 1
                else:
                    skipped_count += 1
                    print(f"  ✗ Skipped")

                # Get next URL
                next_url = self.get_next_url()
                if not next_url:
                    print("\nNo more products (Next button not found or disabled)")
                    break

                # Navigate to next product
                print(f"  → Going to next product...")
                self.driver.get(next_url)
                time.sleep(delay)

            print(f"\n{'='*60}")
            print(f"Complete! Processed: {product_count} | Scraped: {total_scraped} | Skipped: {skipped_count}")
            print(f"{'='*60}")

        finally:
            input("\nPress ENTER to close browser...")
            self.close_driver()


if __name__ == "__main__":
    scraper = StampProductScraper(db_path="stamps.db", headless=False)
    scraper.scrape_all(delay=2.0)
