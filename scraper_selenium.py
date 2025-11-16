from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import re
import time
import json
from typing import List, Dict, Optional, Set
import sqlite3


class StampScraper:
    def __init__(self, db_path: str = "stamps.db", headless: bool = True):
        self.start_url = "https://www.mysticstamp.com/foreign-stamps/?tab=products#/pageSize:96"
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

    def close_popups(self):
        """Close modal popups and accept cookies"""
        # Close modal popup if present
        try:
            close_button = self.driver.find_element(By.CSS_SELECTOR, 'button.klaviyo-close-form')
            close_button.click()
            print("  Closed modal popup")
            time.sleep(1)
        except:
            pass  # No modal present

        # Accept cookies if present
        try:
            cookie_button = self.driver.find_element(By.ID, 'onetrust-accept-btn-handler')
            cookie_button.click()
            print("  Accepted cookies")
            time.sleep(1)
        except:
            pass  # No cookie popup present

    def is_valid_stamp_number(self, stamp_number_text: str) -> bool:
        """Check if stamp number contains only a single number (no ranges, slashes, etc)"""
        parts = stamp_number_text.strip().split()
        if not parts:
            return False

        # The last part should be the number
        number_part = parts[-1]

        # Check if it's just digits (single number)
        return number_part.isdigit()

    def extract_stamp_data(self, listing) -> Optional[Dict]:
        """Extract data from a single stamp listing WebElement"""
        try:
            # Get product ID from article tag inside li
            article = listing.find_element(By.CSS_SELECTOR, 'article.ss__result__inner')
            product_id = article.get_attribute('data-product-id')
            if not product_id or product_id in self.scraped_ids:
                return None

            # Extract image URL
            try:
                img_element = listing.find_element(By.CSS_SELECTOR, 'img.card-image')
                image_url = img_element.get_attribute('src')
            except:
                return None

            # Skip if image is "coming soon" placeholder
            if 'new-image-coming-soon.jpg' in image_url:
                return None

            # Extract stamp number
            try:
                stamp_number_element = listing.find_element(By.CSS_SELECTOR, 'a.StampNumber')
                stamp_number_text = stamp_number_element.text.strip()

                # If text is empty, try getting from innerHTML or data attribute
                if not stamp_number_text:
                    stamp_number_text = stamp_number_element.get_attribute('innerHTML').strip()
            except:
                return None

            # Skip if still empty
            if not stamp_number_text:
                return None

            # Validate stamp number (must be single number only)
            if not self.is_valid_stamp_number(stamp_number_text):
                return None

            # Extract year and country
            try:
                title_element = listing.find_element(By.CSS_SELECTOR, 'a.card-ellipsis span')
                title_text = title_element.text.strip()

                # If text is empty, try getting from innerHTML
                if not title_text:
                    title_text = title_element.get_attribute('innerHTML').strip()
            except:
                return None

            # Skip if still empty
            if not title_text:
                return None

            # Extract year (first 4 digits)
            year_match = re.match(r'(\d{4})', title_text)
            if not year_match:
                return None
            year = year_match.group(1)

            # Extract country (text after year and space)
            country = title_text[4:].strip()

            # Extract price
            try:
                price_element = listing.find_element(By.CSS_SELECTOR, 'span.price--withoutTax')
                price_text = price_element.text.strip()

                # If text is empty, try getting from innerHTML
                if not price_text:
                    price_text = price_element.get_attribute('innerHTML').strip()
            except:
                return None

            # Skip if still empty
            if not price_text:
                return None

            # Extract numeric value from price
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

    def scrape_current_listings(self) -> List[Dict]:
        """Scrape currently visible listings and return new stamp data"""
        try:
            # Close any popups that might have appeared
            self.close_popups()

            # Wait for listings to load
            wait = WebDriverWait(self.driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'li.ss__result')))

            # Scroll to bottom to trigger lazy loading
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Scroll back to top
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Give extra time for all elements to load
            time.sleep(2)

            # Find all stamp listings
            listings = self.driver.find_elements(By.CSS_SELECTOR, 'li.ss__result')
            print(f"  Found {len(listings)} total listings on page")

            stamps = []
            for listing in listings:
                stamp_data = self.extract_stamp_data(listing)
                if stamp_data:
                    stamps.append(stamp_data)

            return stamps

        except Exception as e:
            print(f"  Error scraping listings: {e}")
            return []

    def click_show_more(self) -> bool:
        """Click the Show More button. Returns True if successful, False if not found."""
        try:
            # Check for popups before clicking
            self.close_popups()

            # Scroll to bottom where button is located
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)

            # Wait for Show More button to be present and clickable
            wait = WebDriverWait(self.driver, 10)
            show_more_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.button.button--transparent'))
            )

            print("  Clicking 'Show More' button...")
            # Use JavaScript click as backup
            self.driver.execute_script("arguments[0].scrollIntoView(true);", show_more_button)
            time.sleep(1)
            show_more_button.click()

            # Wait for new items to load
            time.sleep(4)

            # Check for popups after clicking (modal might appear)
            self.close_popups()

            return True

        except Exception as e:
            print(f"  Show More button not found or not clickable")
            return False

    def scrape_all(self, delay: float = 2.0, max_clicks: Optional[int] = None):
        """
        Scrape all listings by clicking Show More button

        Args:
            delay: Delay between clicks in seconds
            max_clicks: Maximum number of Show More clicks (None for unlimited)
        """
        self.init_driver()

        try:
            # Navigate to starting URL
            print(f"Loading: {self.start_url}")
            self.driver.get(self.start_url)
            time.sleep(3)

            # Close popups
            print("\nChecking for popups...")
            self.close_popups()
            time.sleep(2)

            click_count = 0
            total_scraped = 0
            consecutive_no_new = 0

            while True:
                print(f"\n--- Scrape iteration {click_count + 1} ---")

                # Scrape current listings
                stamps = self.scrape_current_listings()

                if stamps:
                    print(f"  ✓ Found {len(stamps)} new valid stamps")
                    self.save_to_database(stamps)
                    self.save_to_json_incremental(stamps)
                    total_scraped += len(stamps)
                    consecutive_no_new = 0
                else:
                    consecutive_no_new += 1
                    print(f"  ✗ No new valid stamps")

                # Stop if no new data for 3 iterations
                if consecutive_no_new >= 3:
                    print("\nNo new data in last 3 iterations. Stopping.")
                    break

                # Check if we've reached max clicks
                if max_clicks and click_count >= max_clicks:
                    print(f"\nReached maximum clicks: {max_clicks}")
                    break

                # Click Show More button
                if not self.click_show_more():
                    print("\nShow More button not available. Reached end of listings.")
                    break

                click_count += 1
                time.sleep(delay)

            print(f"\n{'='*60}")
            print(f"Scraping complete!")
            print(f"Total Show More clicks: {click_count}")
            print(f"Total stamps scraped: {total_scraped}")
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
    # Initialize scraper (headless=False to see browser window for debugging)
    scraper = StampScraper(db_path="stamps.db", headless=False)

    # Scrape all pages with 2 second delay between requests
    scraper.scrape_all(delay=2.0)

    # Export to JSON
    scraper.export_to_json("stamps.json")
