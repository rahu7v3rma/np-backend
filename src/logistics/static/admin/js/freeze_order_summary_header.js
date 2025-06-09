document.addEventListener('DOMContentLoaded', function () {
    const table = document.querySelector('.change-list #result_list');
    if (table) {
        const wrapper = document.createElement('div');
        wrapper.style.maxHeight = '750px';
        wrapper.style.overflowY = 'auto';

        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);

        // Add sticky styling via JS (in case CSS fails)
        const ths = table.querySelectorAll('thead th');
        ths.forEach(th => {
            th.style.position = 'sticky';
            th.style.top = '0';
            th.style.zIndex = '1000';
        });
    }
});
