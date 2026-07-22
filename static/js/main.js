// === АВТООПРЕДЕЛЕНИЕ ЧАСОВОГО ПОЯСА ===
(function() {
    // Проверяем, есть ли select с часовыми поясами на странице
    const timezoneSelect = document.getElementById('timezone-select');
    if (timezoneSelect) {
        // Если есть — определяем часовой пояс
        try {
            const detectedTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            
            // Проверяем, есть ли такой вариант в select
            let found = false;
            for (let option of timezoneSelect.options) {
                if (option.value === detectedTimezone) {
                    option.selected = true;
                    found = true;
                    break;
                }
            }
            
            // Если не нашли — пытаемся найти по смещению
            if (!found) {
                const offset = -new Date().getTimezoneOffset() / 60;
                const offsetStr = offset >= 0 ? `UTC+${offset}` : `UTC${offset}`;
                
                for (let option of timezoneSelect.options) {
                    if (option.text.includes(offsetStr)) {
                        option.selected = true;
                        break;
                    }
                }
            }
        } catch (e) {
            console.log('Автоопределение времени не удалось:', e);
        }
    }
})();

// === ПРОВЕРКА ПОДКЛЮЧЕНИЯ К VK ===
function testVKConnection(vkToken, groupId) {
    const result = document.getElementById('test-result');
    if (!result) return;
    
    result.innerHTML = '⏳ Проверка...';
    result.style.color = 'var(--warning)';
    
    fetch('/api/test-vk', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            vk_token: vkToken,
            group_id: groupId
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            result.innerHTML = '✅ ' + data.message;
            result.style.color = 'var(--success)';
        } else {
            result.innerHTML = '❌ ' + data.message;
            result.style.color = 'var(--danger)';
        }
    })
    .catch(() => {
        result.innerHTML = '❌ Ошибка соединения';
        result.style.color = 'var(--danger)';
    });
}

// === ПРОВЕРКА ГРУППЫ (из groups.html) ===
function testGroupConnection(groupId) {
    const result = document.getElementById('test-result-' + groupId);
    if (!result) return;
    
    result.innerHTML = '⏳ Проверка...';
    result.style.color = 'var(--warning)';
    
    fetch('/api/test-vk-group/' + groupId)
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                result.innerHTML = '✅ ' + data.message;
                result.style.color = 'var(--success)';
            } else {
                result.innerHTML = '❌ ' + data.message;
                result.style.color = 'var(--danger)';
            }
        })
        .catch(() => {
            result.innerHTML = '❌ Ошибка соединения';
            result.style.color = 'var(--danger)';
        });
}

console.log('🚀 SMM Пилот загружен!');
