import asyncio
import logging
import os
from urllib.parse import quote
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

# Налаштування логування
logging.basicConfig(
    filename="parser.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)
logger = logging.getLogger("DetalParser")

BM_USER = os.getenv("BM_USER")
BM_PASS = os.getenv("BM_PASS")
STATE_FILE = "state.json"

def _fetch_sync(part_number: str) -> dict:
    # Безпечне кодування артикула для URL (враховує слеши та пробіли)
    encoded_part = quote(part_number.strip())
    external_url = f"https://b2b.bm.parts/catalog?q={encoded_part}&save=true&search_mode=strict"
    login_url = "https://login.bm.parts/login?next=%2F%2Fb2b.bm.parts"
    captured_data = {}

    logger.info(f"Початок роботи для артикула: {part_number}")

    has_state = os.path.exists(STATE_FILE)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        
        # Налаштовуємо контекст: якщо є збережена сесія, підтягуємо її
        context_kwargs = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if has_state:
            context_kwargs["storage_state"] = STATE_FILE

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        # Слухаємо мережу: перехоплюємо ТІЛЬКИ основний запит товарів (без агрегацій)
        def handle_response(response):
            nonlocal captured_data
            if "api.bm.parts/search/products" in response.url and "aggregations" not in response.url:
                logger.info(f"Знайдено основний запит товарів до API: {response.url} [Status: {response.status}]")
                try:
                    data = response.json()
                    if isinstance(data, dict) and "products" in data:
                        captured_data = data
                        logger.info("JSON-відповідь із товарами успішно перехоплена.")
                except Exception as e:
                    logger.error(f"Помилка парсингу JSON: {e}")

        page.on("response", handle_response)

        try:
            if not has_state:
                # Первинний вхід виконується лише якщо файл state.json ще відсутній
                logger.info("Файл сесії відсутній. Виконуємо вхід...")
                page.goto(login_url, timeout=20000)
                page.fill("#login", BM_USER)
                page.fill("#password", BM_PASS)
                page.click("button:has-text('Увійти')")
                page.wait_for_timeout(4000)
                
                # Зберігаємо сесію для всіх наступних запитів
                context.storage_state(path=STATE_FILE)
                logger.info("Сесію успішно збережено у state.json")
            else:
                logger.info("Використовуємо збережену сесію (без повторного логіну).")

            # Переходимо до пошуку конкретної деталі
            logger.info(f"Перехід до каталогу за посиланням: {external_url}")
            page.goto(external_url, timeout=20000)
            page.wait_for_timeout(4000)  # Очікуємо виконання API-запиту

        except Exception as e:
            logger.error(f"Помилка під час автоматизації Playwright: {e}")
        finally:
            browser.close()

    products = captured_data.get("products", []) if isinstance(captured_data, dict) else []
    
    if products and isinstance(products, list) and len(products) > 0:
        first_item = products[0]
        raw_price = first_item.get("price") or first_item.get("min_price") or 0.0
        parsed_price = float(raw_price) if raw_price else 0.0
        item_part = first_item.get("article", part_number)
        
        logger.info(f"Успішно знайдено товар: {item_part} з ціною {parsed_price}")
        return {
            "site": "BM Parts",
            "part_number": item_part,
            "price": parsed_price,
            "url": external_url
        }

    logger.warning(f"Товар за артикулом {part_number} не знайдено або дані не перехоплено.")
    return {
        "site": "BM Parts",
        "part_number": part_number,
        "price": 0.0,
        "url": external_url
    }

async def fetch_from_bm_parts(part_number: str) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_sync, part_number)

async def get_all_prices(part_number: str):
    return [await fetch_from_bm_parts(part_number)]