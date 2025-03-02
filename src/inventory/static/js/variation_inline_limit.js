var variationMapping = null;

const setVariation =(new_variation)=>{
    variationMapping=new_variation
}

document.addEventListener('DOMContentLoaded', function () {
    toggleVariationGroupVisibility()
    const inlineLimit = 5;
    const checkInlineCount = function () {
        const productVariationGroup = Array.from(document.querySelectorAll('[id^="id_productvariation_set-"][id$="-variation"]'))
            .filter(select => !select.id.includes('__prefix__'));
        const addButton = Array.from(document.querySelectorAll('.add-row a')).find(button => button.textContent.includes('Add another Product Variation'));
        if (productVariationGroup.length >= inlineLimit) {
            if (addButton) {
                addButton.style.display = 'none';
            }
        } else {
            if (addButton) {
                addButton.style.display = '';
            }
        }
    };

    checkInlineCount();

    document.addEventListener('click', function (event) {
        if (event.target && event.target.matches('.add-row a')) {
            setTimeout(checkInlineCount, 50);
        }
        toggleVariationGroupVisibility()
    });
});

const toggleVariationGroupVisibility = ()=>{
    const selectElements = Array.from(document.querySelectorAll('[id^="id_productvariation_set-"][id$="-variation"]'))
            .filter(select => !select.id.includes('__prefix__'));  // Exclude elements with __prefix__
        function updateGroupVisibility(select) {
            const selectedText = select.options[select.selectedIndex].text;
            const selectIndex = select.id.match(/productvariation_set-(\d+)-variation/)[1];

            const textVariationGroup = document.getElementById(`productvariation_set-${selectIndex}-producttextvariation_set-group`);
            const colorVariationGroup = document.getElementById(`productvariation_set-${selectIndex}-productcolorvariationimage_set-group`);

            if (textVariationGroup) textVariationGroup.classList.add('hidden');
            if (colorVariationGroup) colorVariationGroup.classList.add('hidden');

            if (selectedText !== "" && selectedText !== "---------") {
                const isColor = variationMapping.COLOR.includes(selectedText);
                const isText = variationMapping.TEXT.includes(selectedText);

                if (isColor && colorVariationGroup) {
                    colorVariationGroup.classList.remove('hidden');
                } else if (isText && textVariationGroup) {
                    textVariationGroup.classList.remove('hidden');
                }
            }
        }

        selectElements.forEach(select => {
            updateGroupVisibility(select);
        });

        selectElements.forEach(select => {
            select.addEventListener('change', function () {
                updateGroupVisibility(select);
            });
        });
}
