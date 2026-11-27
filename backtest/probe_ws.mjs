// Read one head notification from the candidate public WSS endpoint.
import { writeFileSync } from 'node:fs';
const url = 'wss://mainnet.hsk.xyz';
const evidence = { url, queried_at: new Date().toISOString(), method: 'eth_subscribe', evidence: 'UNVERIFIED' };
const socket = new WebSocket(url);
let done = false;
function finish(extra) {
  if (done) return;
  done = true;
  Object.assign(evidence, extra);
  writeFileSync('config/network/websocket.json', JSON.stringify(evidence, null, 2) + '\n');
  process.exit(0);
}
setTimeout(() => finish({error:'timed out after 15 seconds'}), 15000);
socket.onopen = () => socket.send(JSON.stringify({jsonrpc:'2.0', id:1, method:'eth_subscribe', params:['newHeads']}));
socket.onerror = e => finish({error:String(e.message ?? e.type)});
socket.onclose = e => finish({error:'closed', code:e.code});
socket.onmessage = e => {
  const message = JSON.parse(e.data);
  if (message.error) finish({error:message.error});
  if (message.id === 1) evidence.subscription = message.result;
  if (message.method === 'eth_subscription' && evidence.subscription === message.params.subscription)
    finish({evidence:'OBSERVED_MAINNET', header:message.params.result});
};
