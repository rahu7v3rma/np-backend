document.addEventListener('DOMContentLoaded', function() {
    document.querySelector("#changelist-filter > details:nth-child(7) > summary").textContent = "By Organization"
});

document.addEventListener("DOMContentLoaded", function () {
    const filterContainer = document.getElementById("changelist-filter");
    if (!filterContainer) return;
    const listItems = filterContainer.querySelectorAll("li");
    listItems.forEach(li => {
        const link = li.querySelector("a");
        if (link) {
            const href = link.getAttribute("href");
            if (href.includes("product_id__employee_group_campaign_id__campaign__status__exact=PENDING") ||
                href.includes("product_id__employee_group_campaign_id__campaign__status__exact=OFFER")) {
                li.remove();
            }
        }
    });
});
