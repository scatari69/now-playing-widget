const copy = document.querySelector('#copy');
if (copy) copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(document.querySelector('#link').value); copy.textContent = 'Скопировано'; } catch { document.querySelector('#link').select(); copy.textContent = 'Скопируйте ссылку'; } });
