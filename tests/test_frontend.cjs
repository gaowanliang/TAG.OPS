const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
function element(id) {
    if (!elements.has(id)) elements.set(id, {value: '', textContent: '', hidden: true});
    return elements.get(id);
}
const storage = new Map();
const requests = [];
let reply = {accepted: false};
let fail = false;
const context = {
    document: {getElementById: element, addEventListener() {}},
    localStorage: {getItem: k => storage.get(k) ?? null,
        setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k)},
    fetch: async (url, options) => {
        requests.push([url, options]);
        if (fail) throw new Error('offline');
        return {ok: true, json: async () => reply};
    },
    console,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('app/web/static/app.js', 'utf8'), context);

(async () => {
    assert.equal(await context.showConfirm('确认', '执行操作？'), false);
    assert.equal(requests.at(-1)[0], '/api/dialog');
    assert.equal(JSON.parse(requests.at(-1)[1].body).kind, 'confirm');
    assert.equal(element('dialog-modal').hidden, true);
    reply = {accepted: true};
    assert.equal(await context.showConfirm('确认', '执行操作？'), true);
    fail = true;
    assert.equal(await context.showConfirm('确认', '执行操作？'), false);
    assert.equal(element('pmsg').textContent, 'offline');
    fail = false;

    element('folder-path').value = 'D:\\old';
    reply = {path: null};
    await context.openBrowser('folder-path');
    assert.equal(element('folder-path').value, 'D:\\old');
    reply = {path: 'D:\\图片'};
    await context.openBrowser('folder-path');
    assert.equal(element('folder-path').value, reply.path);
    let destination;
    await context.openBrowser({onPick: path => {destination = path;}});
    assert.equal(destination, reply.path);
    assert.equal(element('browser-modal').hidden, true);

    requests.length = 0;
    vm.runInContext("state.source = 'upload'", context);
    await context.refreshCategories();
    assert.equal(requests.length, 1);
    assert.equal(requests[0][0], '/api/dialog');
    assert.match(JSON.parse(requests[0][1].body).message, /文件夹模式/);

    const hardware = {selected: 'DmlExecutionProvider', gpus_indexed: [
        {id: 0, name: 'Intel', memory_bytes: 512 * 2**20},
        {id: 3, name: 'NVIDIA', memory_bytes: 8 * 2**30},
    ]};
    storage.set('aict_device_id', '1');
    context.populateGpuSelect(hardware);
    assert.equal(storage.has('aict_device_id'), false);
    element('gpu-device').value = '3';
    element('gpu-device').onchange();
    context.populateGpuSelect(hardware);
    assert.equal(element('gpu-device').value, '3');
    assert.match(element('gpu-device').innerHTML, /8.0 GiB/);
    context.populateGpuSelect({...hardware, selected: 'CUDAExecutionProvider'});
    assert.equal(storage.has('aict_device_id'), false);
    console.log('Frontend checks passed: native dialogs, cancel/failure, folder callbacks, category restriction, GPU settings.');
})().catch(error => {console.error(error); process.exitCode = 1;});
