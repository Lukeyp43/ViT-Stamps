from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

# Initialize browser
chrome_options = Options()
chrome_options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(options=chrome_options)

try:
    url = "https://www.mysticstamp.com/foreign-stamps/?tab=products#/pageSize:96"
    print(f"Loading: {url}")
    driver.get(url)
    time.sleep(5)

    # Scroll to bottom
    print("\nScrolling to bottom...")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)

    print("\n=== LOOKING FOR SHOW MORE BUTTON ===\n")

    # Try different selectors
    selectors = [
        'a.button.button--transparent',
        'a.button--transparent',
        'a[href*="productsPage"]',
        'button:contains("Show More")',
        'a:contains("Show More")',
    ]

    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            print(f"Selector '{selector}': Found {len(elements)} elements")
            for i, elem in enumerate(elements[:3]):
                print(f"  Element {i+1}:")
                print(f"    Text: {elem.text}")
                print(f"    HTML: {elem.get_attribute('outerHTML')[:200]}")
        except Exception as e:
            print(f"Selector '{selector}': Error - {e}")

    # Look for all buttons
    print("\n=== ALL BUTTONS ON PAGE ===")
    buttons = driver.find_elements(By.TAG_NAME, 'button')
    print(f"Found {len(buttons)} button elements")

    # Look for all links with "Show" or "More"
    print("\n=== LINKS WITH 'SHOW' OR 'MORE' ===")
    all_links = driver.find_elements(By.TAG_NAME, 'a')
    for link in all_links:
        text = link.text.strip()
        if 'show' in text.lower() or 'more' in text.lower():
            print(f"  Text: '{text}'")
            print(f"  HTML: {link.get_attribute('outerHTML')[:300]}")
            print()

    input("\nPress Enter to close browser...")

finally:
    driver.quit()
