const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  console.log("Navigating to https://toggl-api.vercel.app...");
  try {
    const response = await page.goto('https://toggl-api.vercel.app');
    console.log("Status code:", response.status());
    
    console.log("Waiting for login form...");
    await page.waitForSelector('#email', { timeout: 10000 });
    
    console.log("Entering credentials...");
    await page.fill('#email', 'tukumalu91@gmail.com');
    await page.fill('#password', 'AbGrMy*k@Bx4_7U');
    
    console.log("Clicking login...");
    await page.click('#login-btn');
    
    console.log("Waiting for navigation to homepage/dashboard...");
    await page.waitForSelector('text=Toggl Time Journal', { timeout: 15000 });
    
    console.log("Login and render test successful!");
    await page.screenshot({ path: 'playwright-success.png' });
  } catch (err) {
    console.error("Test failed:", err.message);
    const content = await page.content();
    console.log("HTML Content:", content.substring(0, 1000));
    await page.screenshot({ path: 'playwright-error.png' });
  } finally {
    await browser.close();
  }
})();
