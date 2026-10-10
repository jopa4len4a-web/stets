const mineflayer = require('mineflayer');
const { PNG } = require('pngjs');

const HOST = process.argv[2];
const PORT = parseInt(process.argv[3]);
const COUNT = parseInt(process.argv[4]);
const DELAY = parseInt(process.argv[5]);

const bots = [];

function log(obj) {
    console.log(JSON.stringify(obj));
}

function spawnBot(i) {
    const bot = mineflayer.createBot({
        host: HOST,
        port: PORT,
        username: `SB_${i}_${Date.now().toString(36).slice(-3)}`,
        auth: 'offline',
        version: false,
    });

    bot.once('spawn', () => {
        log({ type: 'ok', i });
    });

    // Ловим смену предмета в руке
    bot.on('heldItemChanged', () => {
        const item = bot.heldItem;
        if (!item) return;
        if (item.name === 'filled_map') {
            const pixels = extractMapPixels(item);
            if (pixels) {
                const png = renderPNG(pixels);
                log({ type: 'captcha_map', i, png_base64: png.toString('base64') });
            }
        }
    });

    // Ловим сообщения в чате
    bot.on('message', (jsonMsg) => {
        const text = jsonMsg.toString();
        if (/капч|ответ|verify|answer|captcha/i.test(text)) {
            log({ type: 'captcha_prompt', i, text });
        }
    });

    bot.on('error', (e) => {
        log({ type: 'fail', i, error: e.message });
    });

    bot.on('kicked', (reason) => {
        log({ type: 'kick', i, reason: typeof reason === 'string' ? reason : JSON.stringify(reason) });
    });

    bots.push(bot);
}

function extractMapPixels(item) {
    // Структура NBT карты
    try {
        const colors = item.nbt.value.map.value.colors.value;
        return colors;
    } catch (e) {
        return null;
    }
}

function renderPNG(colors) {
    const size = 128;
    const png = new PNG({ width: size, height: size });
    for (let i = 0; i < colors.length && i < size * size; i++) {
        const [r, g, b] = mapColorToRGB(colors[i]);
        const idx = i * 4;
        png.data[idx] = r;
        png.data[idx + 1] = g;
        png.data[idx + 2] = b;
        png.data[idx + 3] = 255;
    }
    return PNG.sync.write(png);
}

function mapColorToRGB(c) {
    // Стандартная палитра карт Minecraft (упрощённая)
    const palette = [
        [0, 0, 0], [127, 178, 56], [247, 233, 163], [199, 199, 199], [255, 0, 0],
        [160, 160, 255], [167, 167, 167], [0, 124, 0], [255, 255, 255], [164, 168, 184],
        [151, 109, 77], [112, 112, 112], [64, 64, 64], [143, 119, 72], [255, 252, 245],
        [216, 127, 51], [178, 76, 216], [102, 153, 216], [229, 229, 51], [127, 204, 25],
        [242, 127, 165], [76, 76, 76], [153, 153, 153], [76, 127, 153], [127, 63, 178],
        [51, 76, 178], [102, 127, 51], [102, 76, 51], [166, 155, 143], [178, 178, 178],
        [0, 0, 255], [0, 255, 0], [255, 255, 0], [255, 0, 255], [0, 255, 255],
        [255, 255, 255]
    ];
    const base = (c >> 2) & 0x3F;
    const shade = c & 0x3;
    let [r, g, b] = palette[base] || [0, 0, 0];
    const mult = [180, 220, 255, 135][shade] / 255;
    return [Math.floor(r * mult), Math.floor(g * mult), Math.floor(b * mult)];
}

// Слушаем команды от Python — писать в чат
process.stdin.on('data', (data) => {
    try {
        const msg = JSON.parse(data.toString().trim());
        if (msg.type === 'say' && msg.bot_id !== undefined) {
            const bot = bots[msg.bot_id - 1];
            if (bot) bot.chat(msg.text);
        }
    } catch (e) {}
});

// Запуск ботов
for (let i = 1; i <= COUNT; i++) {
    setTimeout(() => spawnBot(i), i * DELAY);
}

process.on('SIGTERM', () => {
    bots.forEach(b => { try { b.quit(); } catch (e) {} });
    process.exit(0);
});
