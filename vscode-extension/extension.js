// Icosele VM VSCode Extension
// Communicates with the local REST API at localhost:47820
// Uses only built-in Node.js http module — no npm dependencies.

const vscode = require('vscode');
const http = require('http');

const API_BASE = 'http://localhost:47820';
let statusBarItem;

function apiRequest(path, method, body) {
    return new Promise((resolve, reject) => {
        const url = new URL(path, API_BASE);
        const opts = {
            hostname: url.hostname,
            port: url.port,
            path: url.pathname,
            method: method || 'GET',
            headers: { 'Content-Type': 'application/json' },
            timeout: 5000,
        };
        const req = http.request(opts, (res) => {
            let data = '';
            res.on('data', (chunk) => { data += chunk; });
            res.on('end', () => {
                try {
                    resolve({ status: res.statusCode, data: JSON.parse(data) });
                } catch (e) {
                    resolve({ status: res.statusCode, data: data });
                }
            });
        });
        req.on('error', (err) => {
            reject(new Error(
                'Cannot connect to Icosele VM. ' +
                'Make sure the app is running and the REST API is enabled on port 47820.'
            ));
        });
        req.on('timeout', () => { req.destroy(); reject(new Error('Request timed out')); });
        if (body) req.write(JSON.stringify(body));
        req.end();
    });
}

async function showError(msg) {
    vscode.window.showErrorMessage(msg);
}

async function listVMs() {
    try {
        const { data } = await apiRequest('/api/vms', 'GET');
        const items = (data.vms || []).map(vm => ({
            label: vm.name,
            description: `${vm.status} | ${vm.ram_mb}MB | ${vm.cpu_cores} cores`,
            vm: vm,
        }));
        const picked = await vscode.window.showQuickPick(items, { placeHolder: 'Select a VM' });
        return picked ? picked.vm : null;
    } catch (e) {
        showError(e.message);
        return null;
    }
}

async function startVM() {
    const vm = await listVMs();
    if (!vm) return;
    try {
        await apiRequest(`/api/vms/${vm.vm_id}/start`, 'POST');
        vscode.window.showInformationMessage(`Starting VM: ${vm.name}`);
    } catch (e) { showError(e.message); }
}

async function stopVM() {
    const vm = await listVMs();
    if (!vm) return;
    try {
        await apiRequest(`/api/vms/${vm.vm_id}/stop`, 'POST');
        vscode.window.showInformationMessage(`Stopping VM: ${vm.name}`);
    } catch (e) { showError(e.message); }
}

async function takeSnapshot() {
    const vm = await listVMs();
    if (!vm) return;
    const name = await vscode.window.showInputBox({ prompt: 'Snapshot name', value: 'vscode-snapshot' });
    if (!name) return;
    try {
        await apiRequest(`/api/vms/${vm.vm_id}/snapshot`, 'POST', { name });
        vscode.window.showInformationMessage(`Snapshot '${name}' created for ${vm.name}`);
    } catch (e) { showError(e.message); }
}

function openDashboard() {
    vscode.env.openExternal(vscode.Uri.parse('http://localhost:47820'));
}

async function updateStatusBar() {
    try {
        const { data } = await apiRequest('/api/vms', 'GET');
        const running = (data.vms || []).filter(vm => vm.status === 'running').length;
        const total = (data.vms || []).length;
        statusBarItem.text = `$(vm) ${running}/${total} VMs`;
        statusBarItem.show();
    } catch (e) {
        statusBarItem.text = '$(vm) Vault offline';
        statusBarItem.show();
    }
}

function activate(context) {
    context.subscriptions.push(
        vscode.commands.registerCommand('icosele-vm.listVMs', listVMs),
        vscode.commands.registerCommand('icosele-vm.startVM', startVM),
        vscode.commands.registerCommand('icosele-vm.stopVM', stopVM),
        vscode.commands.registerCommand('icosele-vm.takeSnapshot', takeSnapshot),
        vscode.commands.registerCommand('icosele-vm.openDashboard', openDashboard),
        vscode.commands.registerCommand('icosele-vm.status', updateStatusBar),
    );
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'icosele-vm.listVMs';
    context.subscriptions.push(statusBarItem);
    updateStatusBar();
    setInterval(updateStatusBar, 30000);
}

function deactivate() {}

module.exports = { activate, deactivate };
