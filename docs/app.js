const W = 32, H = 32, N = W * H, BYTES = N * 2;
let port = null;
let reader = null;
let keepReading = false;
let buf = new Uint8Array(0);
let mode = null; // 'raw' | 'framed'
let latest = null; // Float32Array of 1024
let frames = 0;
let rxBytes = 0;
let paletteName = 'iron_red';
let autoRange = true;
let vmin = 15, vmax = 30;

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const imgData = ctx.createImageData(W, H);

// ---------- palettes (port of thermalview/palette.py) ----------
function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }
function tNorm(c, vmin, vmax) {
  if (vmax <= vmin) return new Float64Array(c.length);
  const out = new Float64Array(c.length);
  for (let i = 0; i < c.length; i++) out[i] = clamp((c[i]-vmin)/(vmax-vmin), 0, 1);
  return out;
}
function stackRGB(r,g,b) {
  const out = new Uint8ClampedArray(r.length*3);
  for (let i=0;i<r.length;i++){ out[i*3]=r[i]|0; out[i*3+1]=g[i]|0; out[i*3+2]=b[i]|0; }
  return out;
}
const palettes = {
  iron_red: (t) => {
    const r=new Float64Array(t.length), g=new Float64Array(t.length), b=new Float64Array(t.length);
    for(let i=0;i<t.length;i++){
      const x=t[i];
      r[i]= x<=0.5 ? x*180 : (x<=0.8 ? 255 : 255);
      g[i]= x<=0.5 ? 0 : (x<=0.8 ? x*255 : 253);
      b[i]= x<=0.5 ? x*120 : (x<=0.8 ? 0 : 238);
    }
    return stackRGB(r,g,b);
  },
  rainbow: (t) => {
    const r=new Float64Array(t.length), g=new Float64Array(t.length), b=new Float64Array(t.length);
    for(let i=0;i<t.length;i++){
      const x=t[i];
      let R,G,B;
      if(x<=0.2){R=0;G=0;B=0;}
      else if(x<=0.4){R=0x1A;G=0x23;B=0x7E;}
      else if(x<=0.5){R=0x3F;G=0x51;B=0xB5;}
      else if(x<=0.6){R=0x4C;G=0xAF;B=0x50;}
      else if(x<=0.75){R=0x76;G=0xFF;B=0x03;}
      else if(x<=0.8){R=0xFF;G=0xEB;B=0x3B;}
      else {R=0xF4;G=0x43;B=0x36;}
      r[i]=R;g[i]=G;b[i]=B;
    }
    return stackRGB(r,g,b);
  },
  white_hot: (t) => {
    const v=new Float64Array(t.length);
    for(let i=0;i<t.length;i++) v[i]=t[i]*255;
    return stackRGB(v,v,v);
  },
  blue_orange: (t) => {
    const r=new Float64Array(t.length), g=new Float64Array(t.length), b=new Float64Array(t.length);
    for(let i=0;i<t.length;i++){
      const x=t[i];
      r[i]=x*255; g[i]= x<=0.5 ? 0 : x*120; b[i]= -255*x+255;
    }
    return stackRGB(r,g,b);
  },
  blue_yellow: (t) => {
    const r=new Float64Array(t.length), g=new Float64Array(t.length), b=new Float64Array(t.length);
    for(let i=0;i<t.length;i++){
      const x=t[i];
      if(x<=0.5){ r[i]=x*70; g[i]=x*70; b[i]=x*200; }
      else if(x<=0.82){ r[i]=255; g[i]=255; b[i]=0; }
      else { r[i]=255; g[i]=253; b[i]=238; }
    }
    return stackRGB(r,g,b);
  },
};

// ---------- rendering ----------
function render() {
  if (!latest) return;
  const c = latest;
  let vminEff = vmin, vmaxEff = vmax;
  if (autoRange) {
    let mn=Infinity, mx=-Infinity;
    for (let i=0;i<c.length;i++){ if(c[i]<mn)mn=c[i]; if(c[i]>mx)mx=c[i]; }
    vminEff = mn; vmaxEff = mx;
    if (vmaxEff - vminEff < 6) vmaxEff = vminEff + 6; // app rule-ish
  }
  const t = tNorm(c, vminEff, vmaxEff);
  const rgb = palettes[paletteName](t);
  for (let i=0;i<N;i++){ imgData.data[i*4]=rgb[i*3]; imgData.data[i*4+1]=rgb[i*3+1]; imgData.data[i*4+2]=rgb[i*3+2]; imgData.data[i*4+3]=255; }
  ctx.putImageData(imgData,0,0);
  // scale up via css already (canvas 32x32 displayed 480x480)
  // stats
  let mn=Infinity,mx=-Infinity,sum=0;
  for(let i=0;i<c.length;i++){ if(c[i]<mn)mn=c[i]; if(c[i]>mx)mx=c[i]; sum+=c[i]; }
  document.getElementById('min').textContent = mn.toFixed(1)+' C';
  document.getElementById('max').textContent = mx.toFixed(1)+' C';
  document.getElementById('mean').textContent = (sum/c.length).toFixed(1)+' C';
  document.getElementById('center').textContent = c[15*W+16].toFixed(1)+' C'; // (16,16) 0-based ~ centre
  // min/max positions
  let minI=0,maxI=0;
  for(let i=1;i<c.length;i++){ if(c[i]<c[minI])minI=i; if(c[i]>c[maxI])maxI=i; }
  document.getElementById('minpos').textContent = (minI%W)+','+Math.floor(minI/W);
  document.getElementById('maxpos').textContent = (maxI%W)+','+Math.floor(maxI/W);
  document.getElementById('frames').textContent = frames;
}

// ---------- web serial ----------
async function connect() {
  if (!('serial' in navigator)) {
    setStatus('Web Serial not supported in this browser. Use Chrome (Android) / Chrome or Edge (desktop).');
    return;
  }
  // Some browsers (e.g. Brave on Android) hide Web Serial behind a flag or
  // block it entirely. Try the filtered picker first, then an unfiltered one.
  const filters = [{ usbVendorId: 0x303A, usbProductId: 0x4001 }];
  try {
    port = await navigator.serial.requestPort({ filters });
  } catch (e1) {
    console.warn('filtered requestPort failed:', e1);
    try {
      port = await navigator.serial.requestPort();
    } catch (e2) {
      console.warn('unfiltered requestPort failed:', e2);
      setStatus('no device selected: ' + (e2 && e2.message ? e2.message : e2));
      return;
    }
  }
  try {
    await port.open({ baudRate: 115200 });
    // Assert DTR/RTS: many adapters (incl. this one) only stream with
    // these control lines asserted.
    try { await port.setSignals({ dataTerminalReady: true, requestToSend: true }); }
    catch (e) { console.warn('setSignals failed', e); }
    await new Promise(r=>setTimeout(r, 300));
  } catch (e) {
    setStatus('open failed: '+e.message); port=null; return;
  }
  keepReading = true;
  document.getElementById('connectBtn').disabled = true;
  document.getElementById('disconnectBtn').disabled = false;
  setStatus('connected');
  readLoop();
}

async function disconnect() {
  keepReading = false;
  try { if (reader) await reader.cancel(); } catch(e){}
  reader = null;
  try { await port.setSignals({ dataTerminalReady: false, requestToSend: false }); } catch(e){}
  try { await port.close(); } catch(e){}
  port = null;
  buf = new Uint8Array(0);
  mode = null;
  rxBytes = 0;
  document.getElementById('connectBtn').disabled = false;
  document.getElementById('disconnectBtn').disabled = true;
  setStatus('disconnected');
}

async function readLoop() {
  while (keepReading && port && port.readable) {
    reader = port.readable.getReader();
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value) appendBytes(value);
      }
    } catch (e) {
      if (keepReading) setStatus('read error: '+e.message);
    } finally {
      try { reader.releaseLock(); } catch(e){}
    }
    await new Promise(r=>setTimeout(r, 100));
  }
}

function appendBytes(chunk) {
  rxBytes += chunk.length;
  setStatus('connected ('+rxBytes+' bytes)');
  const merged = new Uint8Array(buf.length + chunk.length);
  merged.set(buf); merged.set(chunk, buf.length);
  buf = merged;
  // detect mode
  if (mode === null) {
    // look for FRAME_MAGIC 00 80 01 00
    let idx = -1;
    for (let i=0;i+3<buf.length;i++){
      if (buf[i]===0x00 && buf[i+1]===0x80 && buf[i+2]===0x01 && buf[i+3]===0x00){ idx=i; break; }
    }
    if (idx >= 0) mode = 'framed';
    else if (buf.length >= BYTES) mode = 'raw';
  }
  // process
  if (mode === 'raw') {
    while (buf.length >= BYTES) {
      decodeFrame(buf.subarray(0, BYTES));
      buf = buf.subarray(BYTES);
    }
  } else if (mode === 'framed') {
    // find header
    while (true) {
      let idx = -1;
      for (let i=0;i+5<buf.length;i++){
        if (buf[i]===0x00 && buf[i+1]===0x80 && buf[i+2]===0x01 && buf[i+3]===0x00){ idx=i; break; }
      }
      if (idx < 0) { // keep tail
        if (buf.length > 3) buf = buf.subarray(buf.length-3);
        break;
      }
      if (idx > 0) { buf = buf.subarray(idx); }
      if (buf.length < 6 + BYTES) break;
      // payload starts at 6
      decodeFrame(buf.subarray(6, 6+BYTES));
      buf = buf.subarray(6+BYTES);
    }
  }
}

function decodeFrame(bytes) {
  const arr = new Float32Array(N);
  for (let i=0;i<N;i++){
    const lo = bytes[i*2], hi = bytes[i*2+1];
    arr[i] = ((hi<<8)|lo) / 10.0;
  }
  latest = arr;
  frames++;
  render();
}

function setStatus(s){ document.getElementById('status').textContent = s; }

// ---------- wiring ----------
document.getElementById('connectBtn').addEventListener('click', connect);
document.getElementById('disconnectBtn').addEventListener('click', disconnect);
document.getElementById('palette').addEventListener('change', (e)=>{ paletteName=e.target.value; render(); });
document.getElementById('autoRange').addEventListener('change', (e)=>{ autoRange=e.target.checked; render(); });
document.getElementById('vmin').addEventListener('change', (e)=>{ vmin=parseFloat(e.target.value)||vmin; render(); });
document.getElementById('vmax').addEventListener('change', (e)=>{ vmax=parseFloat(e.target.value)||vmax; render(); });
document.getElementById('saveBtn').addEventListener('click', ()=>{
  const a = document.createElement('a');
  a.href = canvas.toDataURL('image/png');
  a.download = 'thermal.png';
  a.click();
});

// scale canvas display
canvas.style.width = '480px';
canvas.style.height = '480px';
