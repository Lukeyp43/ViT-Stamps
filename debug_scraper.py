from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time

# Initialize browser
chrome_options = Options()
chrome_options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(options=chrome_options)

try:
    url = "https://www.mysticstamp.com/foreign-stamps/?tab=products&productsPage=1#/pageSize:96"
    print(f"Loading: {url}")
    driver.get(url)

    # Wait for listings
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'li.ss__result')))
    time.sleep(5)  # Extra time for JS to load

    # Get first listing
    listings = driver.find_elements(By.CSS_SELECTOR, 'li.ss__result')
    print(f"\nFound {len(listings)} listings")

    if listings:
        first = listings[0]
        print("\n=== FIRST LISTING DEBUG ===")

        # Product ID
        product_id = first.get_attribute('data-product-id')
        print(f"Product ID: {product_id}")

        # Image
        try:
            img = first.find_element(By.CSS_SELECTOR, 'img.card-image')
            print(f"Image src: {img.get_attribute('src')}")
        except Exception as e:
            print(f"Image error: {e}")

        # Stamp number
        try:
            stamp_num = first.find_element(By.CSS_SELECTOR, 'a.StampNumber')
            print(f"Stamp number: {stamp_num.text}")
        except Exception as e:
            print(f"Stamp number error: {e}")

        # Title
        try:
            title = first.find_element(By.CSS_SELECTOR, 'a.card-ellipsis span')
            print(f"Title: {title.text}")
        except Exception as e:
            print(f"Title error: {e}")

        # Price
        try:
            price = first.find_element(By.CSS_SELECTOR, 'span.price--withoutTax')
            print(f"Price: {price.text}")
        except Exception as e:
            print(f"Price error: {e}")

        # Print full HTML of first listing
        print("\n=== FIRST LISTING HTML ===")
        print(first.get_attribute('outerHTML')[:1000])

    input("\nPress Enter to close browser...")

finally:
    driver.quit()
