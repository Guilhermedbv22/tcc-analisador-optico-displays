const accepts = {
  installer:/^IrisDesktop-Setup-\d+\.\d+\.\d+-x64\.exe$/,
  portable:/^IrisDesktop-Portable-\d+\.\d+\.\d+-x64\.zip$/,
  source:/^Iris_Desktop_\d+\.\d+\.\d+_Fonte\.zip$/,
};

async function showAvailableDownloads() {
  const response=await fetch('downloads/releases.json',{cache:'no-cache'});
  if(!response.ok)return;
  const manifest=await response.json();
  if(!/^\d+\.\d+\.\d+$/.test(manifest.version))return;
  document.querySelector('#release-version').textContent=manifest.version;
  for(const [type,pattern] of Object.entries(accepts)) {
    const item=manifest.files?.[type];
    if(!item||!pattern.test(item.name)||!item.name.includes(manifest.version)||!/^[a-f0-9]{64}$/.test(item.sha256))continue;
    const path='downloads/'+item.name;
    const file=await fetch(path,{method:'HEAD'});
    if(!file.ok||file.headers.get('content-type')?.includes('text/html'))continue;
    const element=document.querySelector(`[data-download="${type}"]`);
    const link=document.createElement('a');
    link.className='button '+(type==='installer'?'primary':'quiet');
    link.href=path;link.download=item.name;link.textContent='Baixar';
    link.title='SHA-256: '+item.sha256;
    element.querySelector('.download-state').replaceWith(link);
    element.hidden=false;
  }
}
showAvailableDownloads().catch(()=>{});
