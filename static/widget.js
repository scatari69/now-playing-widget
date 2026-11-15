const widget = document.querySelector('#widget');
async function update() {
  try {
    const response = await fetch('/api' + location.pathname, {cache: 'no-store'});
    if (!response.ok) throw Error('request failed');
    const data = await response.json();
    widget.hidden = !data.playing;
    if (data.playing) {
      document.querySelector('#title').textContent = data.title;
      document.querySelector('#artist').textContent = data.artist;
      const art = document.querySelector('#art');
      if (data.image) { art.src = data.image; art.hidden = false; } else { art.removeAttribute('src'); art.hidden = true; }
      document.querySelector('#fill').style.width = (data.duration ? Math.max(0, Math.min(100, data.progress / data.duration * 100)) : 0) + '%';
    }
  } catch { widget.hidden = true; }
  setTimeout(update, 10000);
}
update();
