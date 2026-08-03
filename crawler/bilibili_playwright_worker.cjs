#!/usr/bin/env node
/* Node Playwright backend used when Python Playwright is unavailable. */
const fs = require("fs");
const { chromium } = require("playwright");

function arg(name, fallback = "") {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function bvidOf(value) { return (String(value || "").match(/BV[0-9A-Za-z]{10}/) || [""])[0]; }
function clean(value) { return String(value || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim(); }
function count(value) {
  if (value == null || value === "") return null;
  const t = String(value).replace(/,/g, "").trim();
  const m = t.endsWith("万") ? 10000 : /k$/i.test(t) ? 1000 : 1;
  const n = Number.parseFloat(m === 1 ? t : t.slice(0, -1));
  return Number.isFinite(n) ? Math.round(n * m) : null;
}
function safety(title, body) {
  const text = `${title}\n${body}`.toLowerCase();
  if (["验证码", "安全验证", "captcha", "访问过于频繁", "请求被拦截"].some(x => text.includes(x)))
    return "检测到验证码、安全验证或访问限制，采集已停止。";
  if (["登录后", "请先登录", "扫码登录"].some(x => text.includes(x)))
    return "页面要求登录，请在浏览器内自行完成登录后再重新运行。";
  return "";
}
async function main() {
  const payload = JSON.parse(fs.readFileSync(arg("--input"), "utf8"));
  const outPath = arg("--output");
  const smoke = process.argv.includes("--smoke");
  const result = { videos: [], comments: [], stats: { search_video_hits: 0, videos_read: 0 }, failures: [], stop_reason: "" };
  let browser;
  try {
    const systemChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
    const executablePath = fs.existsSync(systemChrome) ? systemChrome : chromium.executablePath();
    browser = await chromium.launch({
      headless: smoke ? true : Boolean(payload.config.headless),
      executablePath,
    });
    const context = await browser.newContext({ locale: "zh-CN", timezoneId: payload.config.timezone || "Asia/Shanghai" });
    const page = await context.newPage();
    if (smoke) {
      await page.goto("https://www.bilibili.com/", { waitUntil: "domcontentloaded", timeout: 45000 });
      const body = await page.locator("body").innerText({ timeout: 10000 });
      result.stop_reason = safety(await page.title(), body);
      result.smoke = { url: page.url(), title: await page.title(), body_chars: body.length };
    } else {
      const hits = new Map();
      const keywords = [...payload.keywords.core_keywords, ...payload.keywords.experience_keywords];
      for (const keyword of keywords) {
        for (let pageNo = 1; pageNo <= payload.config.max_search_pages_per_keyword; pageNo++) {
          try {
            await page.goto(`https://search.bilibili.com/video?keyword=${encodeURIComponent(keyword)}&page=${pageNo}`, { waitUntil: "domcontentloaded", timeout: 45000 });
            const body = await page.locator("body").innerText({ timeout: 10000 });
            const blocked = safety(await page.title(), body);
            if (blocked) { result.stop_reason = blocked; break; }
            const links = await page.locator('a[href*="www.bilibili.com/video/BV"]').evaluateAll((nodes, kw) => nodes.map(a => ({ href: a.href, title: a.getAttribute("title") || a.textContent || "", keyword: kw })), keyword);
            result.stats.search_video_hits += links.length;
            for (const item of links) {
              const bv = bvidOf(item.href);
              if (bv && !hits.has(bv)) hits.set(bv, { bvid: bv, url: `https://www.bilibili.com/video/${bv}`, query_keyword: keyword, search_title: clean(item.title) });
            }
          } catch (e) { result.failures.push(`search:${keyword}:${pageNo}:${e.name}:${e.message}`); }
          if (result.stop_reason || hits.size >= payload.config.max_videos) break;
          await sleep(1000 * (payload.config.page_delay_seconds[0] || 2.5));
        }
        if (result.stop_reason || hits.size >= payload.config.max_videos) break;
      }
      if (!result.stop_reason) for (const hit of [...hits.values()].slice(0, payload.config.max_videos)) {
        try {
          await page.goto(hit.url, { waitUntil: "domcontentloaded", timeout: 45000 });
          const body = await page.locator("body").innerText({ timeout: 10000 });
          const blocked = safety(await page.title(), body);
          if (blocked) { result.stop_reason = blocked; break; }
          const data = await page.evaluate(() => {
            const v = globalThis.__INITIAL_STATE__?.videoData || {};
            const s = v.stat || {}, o = v.owner || {};
            return { bvid:v.bvid, title:v.title, description:v.desc, author_name:o.name, publish_epoch:v.pubdate,
              views:s.view, danmaku:s.danmaku, comments:s.reply, favorites:s.favorite, coins:s.coin, shares:s.share, likes:s.like };
          });
          const video = { ...hit, ...data };
          result.videos.push(video); result.stats.videos_read++;
          await page.mouse.wheel(0, 1600);
          await page.waitForTimeout(1800);
          const visible = await page.evaluate((bvid) => {
            const root=document.querySelector("bili-comments")?.shadowRoot;
            return [...(root?.querySelectorAll("bili-comment-thread-renderer")||[])].map((thread,index)=>{
              const renderer=thread.shadowRoot?.querySelector("bili-comment-renderer");
              const sr=renderer?.shadowRoot;
              const user=sr?.querySelector("bili-comment-user-info")?.shadowRoot?.querySelector("#user-name");
              const rich=sr?.querySelector("bili-rich-text")?.shadowRoot?.querySelector("#contents");
              const actions=sr?.querySelector("bili-comment-action-buttons-renderer")?.shadowRoot;
              return {comment_id:renderer?.getAttribute("data-id")||`visible-${index}`,parent_id:"0",
                text:(rich?.textContent||"").trim(),publish_time:(actions?.querySelector("#pubdate")?.textContent||"").trim(),
                author_name:(user?.textContent||"").trim(),author_uid:user?.getAttribute("data-user-profile-id")||"",
                likes:(actions?.querySelector("#like #count")?.textContent||"").trim(),bvid};
            }).filter(x=>x.text && x.publish_time && x.author_name);
          }, video.bvid);
          result.comments.push(...visible.slice(0, payload.config.max_comments_per_video));
        } catch (e) { result.failures.push(`${hit.bvid}:${e.name}:${e.message}`); }
        await sleep(1000 * (payload.config.page_delay_seconds[0] || 2.5));
      }
    }
    await context.close();
  } catch (e) {
    result.stop_reason = `Node Playwright 启动失败：${e.name}: ${e.message}`;
  } finally {
    if (browser) await browser.close().catch(() => {});
    fs.writeFileSync(outPath, JSON.stringify(result, null, 2), "utf8");
  }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
