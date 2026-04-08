"""JavaScript extraction snippets for LinkedIn scraping.

LinkedIn uses SDUI with hashed CSS classes that change frequently.
These JS snippets use stable anchors: componentkey attrs, data-urn,
computed styles, and semantic HTML structure.
"""

# Messaging: extract conversation list from /messaging/
JS_CONVERSATIONS = """() => {
    const convos = [];
    const items = document.querySelectorAll('li.msg-conversation-listitem');
    for (const item of items) {
        const nameEl = item.querySelector('h3');
        const name = nameEl ? nameEl.textContent.trim() : '';
        const previewEl = item.querySelector('p.msg-conversation-card__message-snippet-body, p[class*="message-snippet"]');
        const preview = previewEl ? previewEl.textContent.trim() : '';
        const timeEl = item.querySelector('time');
        const time = timeEl ? timeEl.textContent.trim() : '';
        const link = item.querySelector('a[href*="/messaging/thread/"]');
        const threadId = link ? link.href.match(/thread\\/([^/]+)/)?.[1] || '' : '';
        if (name) convos.push({name, preview, time, threadId});
    }
    return convos;
}"""

# Messaging: extract messages from an open thread
JS_THREAD_MESSAGES = """() => {
    const msgs = [];
    const items = document.querySelectorAll('li.msg-s-message-list__event');
    for (const item of items) {
        const senderEl = item.querySelector('.msg-s-message-group__name, [class*="message-group__name"]');
        const sender = senderEl ? senderEl.textContent.trim() : '';
        const timeEl = item.querySelector('time');
        const time = timeEl ? timeEl.textContent.trim() : '';
        const bodyEl = item.querySelector('.msg-s-event-listitem__body, [class*="event-listitem__body"]');
        const body = bodyEl ? bodyEl.textContent.trim() : '';
        if (body) msgs.push({sender, time, body});
    }
    return msgs;
}"""

# Profile: extract name, headline, location from Topcard + About sections
JS_PROFILE = """() => {
    const r = {};
    const topcard = document.querySelector('section[componentkey*="Topcard"]');
    if (topcard) {
        const h2 = topcard.querySelector('h2');
        if (h2) r.name = h2.textContent.trim();
        const ps = [...topcard.querySelectorAll('p')].map(p => p.textContent.trim()).filter(t => t.length > 1);
        r._topcard_texts = ps;
    }
    const about = document.querySelector('section[componentkey*="About"]');
    if (about) {
        const box = about.querySelector('[data-testid="expandable-text-box"]');
        if (box) {
            r.about = box.textContent.trim();
        } else {
            const ps = [...about.querySelectorAll('p')];
            let best = '';
            for (const p of ps) {
                const t = p.textContent.trim();
                if (t.length > best.length) best = t;
            }
            if (best.length > 20) r.about = best;
        }
    }
    return r;
}"""

# Company: extract about text and tagline from the Overview section
JS_COMPANY_ABOUT = """() => {
    const r = {};
    const sections = document.querySelectorAll('section');
    for (const s of sections) {
        const h2 = s.querySelector('h2');
        if (!h2) continue;
        const title = h2.textContent.trim().toLowerCase().replace(/[\\u2018\\u2019\\u0060]/g, "'");
        if (title.includes('overview') || title.includes("vue d'ensemble")) {
            const ps = [...s.querySelectorAll('p')];
            let best = '';
            for (const p of ps) {
                const t = p.textContent.trim();
                if (t.length > best.length) best = t;
            }
            if (best.length > 30) r.about = best;
            break;
        }
    }
    const h1 = document.querySelector('h1');
    if (h1) {
        const section = h1.closest('section') || h1.parentElement;
        if (section) {
            const ps = [...section.querySelectorAll('p')];
            for (const p of ps) {
                const t = p.textContent.trim();
                if (t.length > 5 && t.length < 200) {
                    r.tagline = t;
                    break;
                }
            }
        }
    }
    return r;
}"""

# People search: extract results using computed font-size/weight to distinguish
# main result names (16px/600) from mutual connection links (12px/400).
JS_PEOPLE_RESULTS = r"""() => {
    const results = [];
    const seen = new Set();
    const links = document.querySelectorAll('a[href*="/in/"]');

    for (const link of links) {
        const text = link.textContent.trim();
        if (text.length < 2 || text.length > 80) continue;
        if (link.parentElement?.tagName !== 'P') continue;

        const style = window.getComputedStyle(link.parentElement);
        if (parseFloat(style.fontSize) < 14 || parseInt(style.fontWeight) < 600) continue;

        const href = link.href?.split('?')[0];
        if (!href || !href.includes('/in/') || seen.has(href)) continue;
        seen.add(href);

        const name = text.replace(/\s+/g, ' ').trim();

        let cardLink = null;
        let el = link.parentElement;
        for (let i = 0; i < 10; i++) {
            if (!el) break;
            if (el.tagName === 'A' && el.href?.includes('/in/')) { cardLink = el; break; }
            el = el.parentElement;
        }

        let headline = '', location = '';
        if (cardLink) {
            const ps = [...cardLink.querySelectorAll('p')]
                .map(p => p.textContent.trim()).filter(t => t.length > 1);
            let passedName = false;
            for (const p of ps) {
                if (p.includes(name.substring(0, Math.min(name.length, 6)))) {
                    passedName = true; continue;
                }
                if (!passedName) continue;
                if (/^[•·]?\s*\d*(st|nd|rd|th|er?|e)?\+?$/i.test(p)) continue;
                if (/^(message|suivre|follow|se connecter|connect)$/i.test(p)) continue;
                if (!headline) headline = p;
                else if (!location) { location = p; break; }
            }
        }

        results.push({name, headline, location, linkedin: href});
    }
    return results;
}"""

# Posts: extract from activity feed using data-urn attributes
JS_POSTS = r"""(maxPosts) => {
    const items = document.querySelectorAll('[data-urn*="urn:li:activity"]');
    const posts = [];
    const seen = new Set();

    for (const item of items) {
        if (posts.length >= maxPosts) break;

        const urn = item.getAttribute('data-urn');
        if (!urn || seen.has(urn)) continue;
        if (urn.includes('comment')) continue;
        seen.add(urn);

        let content = '';
        const divs = item.querySelectorAll('div');
        const skipPattern = /social|actor|action-bar|image|video|comments?-list/i;
        for (const d of divs) {
            const cls = d.className || '';
            if (skipPattern.test(cls)) continue;
            if (d.querySelectorAll('div').length > 3) continue;
            const t = d.textContent.trim();
            if (t.length > content.length && t.length > 30 && t.length < 10000) {
                if (/^\d+\s*$/.test(t.split('\n')[0].trim())) continue;
                content = t;
            }
        }
        if (!content || content.length < 20) continue;

        const activityId = urn.match(/activity:(\d+)/)?.[1];
        const postUrl = activityId ?
            'https://www.linkedin.com/feed/update/urn:li:activity:' + activityId + '/' : '';

        let date = '';
        const subDesc = item.querySelector('[class*="sub-description"]');
        if (subDesc) date = subDesc.textContent.trim().split('•')[0].trim();

        let isRepost = false;
        const header = item.querySelector('[class*="header__text"]');
        if (header) {
            const ht = header.textContent.toLowerCase();
            isRepost = ht.includes('repost') || ht.includes('republié');
        }

        let reactions = 0, comments = 0;
        const socialArea = item.querySelector('[class*="social-activity"], [class*="social-counts"]');
        if (socialArea) {
            const spans = socialArea.querySelectorAll('span');
            for (const s of spans) {
                const st = s.textContent.trim();
                if (/personne|reaction|like|j'aime/i.test(st)) {
                    const m = st.match(/(\d[\d\s,.]*)/);
                    if (m) reactions = parseInt(m[1].replace(/[\s,.]/g, ''));
                }
                if (/comment/i.test(st)) {
                    const m = st.match(/(\d[\d\s,.]*)/);
                    if (m) comments = parseInt(m[1].replace(/[\s,.]/g, ''));
                }
            }
        }

        posts.push({
            content, date, url: postUrl, is_repost: isRepost,
            engagement: {reactions, comments}
        });
    }
    return posts;
}"""
