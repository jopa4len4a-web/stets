const mineflayer = require('mineflayer');
const { PNG } = require('pngjs');

let CONFIG = null;
let bots = [];

function log(obj) {
    console.log(JSON.stringify(obj));
}

function parseProxy(line) {
    const parts = line.split(':');
    if (parts.length === 2) return { host: parts[0], port: parseInt(parts[1]) };
    return { host: parts[0], port: parseInt(parts[1]), user: parts[2], pass: parts[3] };
}

function randomNick() {
    const a = ['Fast','Dark','Red','Blue','Wild','Cool','Free','Neo','Big','Pro','Swift','Sharp','Ice','Fire'];
    const n = ['Wolf','Falcon','Lion','Storm','Blade','Fire','Ghost','King','Fox','Bear','Eagle','Tiger'];
    return `${a[Math.floor(Math.random()*a.length)]}${n[Math.floor(Math.random()*n.length)]}${Math.floor(Math.random()*1000)}`;
}

function makeUsername(i, template) {
    if (template === 'random') return randomNick();
    return template.replace('{i}', i);
}

function spawnBot(i) {
    const nickname = makeUsername(i, CONFIG.nickname);
    const opts = {
        host: CONFIG.host,
        port: CONFIG.port,
        username: nickname,
        auth: 'offline',
        version: CONFIG.version === 'auto' ? false : CONFIG.version,
    };

    if (CONFIG.proxies && CONFIG.proxies.length > 0) {
        const p = parseProxy(CONFIG.proxies[(i - 1) % CONFIG.proxies.length]);
        opts.socksProxy = p;
    }

    const bot = mineflayer.createBot(opts);
    let captchaHandled = false;

    bot.once('spawn', () => {
        log({ type: 'ok', i, username: nickname });

        // Авто-команды после входа
        if (CONFIG.chat_cmds && CONFIG.chat_cmds.length > 0) {
            CONFIG.chat_cmds.forEach((cmd, idx) => {
                setTimeout(() => {
                    try { bot.chat(cmd); } catch (e) {}
                }, (idx + 1) * 1500);
            });
        }

        // Пропуск если нет капчи за 30 сек
        if (CONFIG.skip_if_none) {
            setTimeout(() => {
                if (!captchaHandled) log({ type: 'no_captcha', i });
            }, 30000);
        }
    });

    bot.on('heldItemChanged', () => {
        const item = bot.heldItem;
        if (!item || item.name !== 'filled_map') return;
        const pixels = extractMapPixels(item);
        if (pixels) {
            captchaHandled = true;
            const png = renderPNG(pixels);
            log({ type: 'captcha_map', i, png_base64: png.toString('base64') });
        }
    });

    bot.on('message', (jsonMsg) => {
        const text = jsonMsg.toString();
        if (/капч|captcha|verify|answer|введи|напиши/i.test(text)) {
            captchaHandled = true;
            log({ type: 'captcha_prompt', i, text });
        }
    });

    bot.on('error', (e) => log({ type: 'fail', i, error: e.message }));
    bot.on('kicked', (r) => log({ type: 'kick', i, reason: typeof r === 'string' ? r : JSON.stringify(r) }));

    bots.push(bot);
}

function extractMapPixels(item) {
    try { return item.nbt.value.map.value.colors.value; } catch (e) { return null; }
}

function renderPNG(colors) {
    const size = 128;
    const png = new PNG({ width: size, height: size });
    for (let i = 0; i < colors.length && i < size * size; i++) {
        const [r, g, b] = mapColorToRGB(colors[i]);
        const idx = i * 4;
        png.data[idx] = r; png.data[idx+1] = g; png.data[idx+2] = b; png.data[idx+3] = 255;
    }
    return PNG.sync.write(png);
}

function mapColorToRGB(c) {
    const palette = [
        [0,0,0],[127,178,56],[247,233,163],[199,199,199],[255,0,0],
        [160,160,255],[167,167,167],[0,124,0],[255,255,255],[164,168,184],
        [151,109,77],[112,112,112],[64,64,64],[143,119,72],[255,252,245],
        [216,127,51],[178,76,216],[102,153,216],[229,229,51],[127,204,25],
        [242,127,165],[76,76,76],[153,153,153],[76,127,153],[127,63,178],
        [51,76,178],[102,127,51],[102,76,51],[166,155,143],[178,178,178],
        [0,0,255],[0,255,0],[255,255,0],[255,0,255],[0,255,255],[255,255,255]
    ];
    const base = (c >> 2) & 0x3F;
    const shade = c & 0x3;
    let [r,g,b] = palette[base] || [0,0,0];
    const mult = [180,220,255,135][shade] / 255;
    return [Math.floor(r*mult), Math.floor(g*mult), Math.floor(b*mult)];
}

process.stdin.on('data', (data) => {
    const lines = data.toString().trim().split('\n');
    for (const line of lines) {
        try {
            const msg = JSON.parse(line);
            if (msg.type === 'config') {
                CONFIG = msg;
                for (let i = 1; i <= CONFIG.count; i++) {
                    setTimeout(() => spawnBot(i), i * CONFIG.delay);
                }
            } else if (msg.type === 'say' && msg.bot_id !== undefined) {
                const bot = bots[msg.bot_id - 1];
                if (bot) bot.chat(msg.text);
            } else if (msg.type === 'broadcast') {
                // Все боты пишут одно и то же
                bots.forEach(b => {
                    try { b.chat(msg.text); } catch (e) {}
                });
            }
        } catch (e) {}
    }
});

process.on('SIGTERM', () => {
    bots.forEach(b => { try { b.quit(); } catch (e) {} });
    process.exit(0);
});
