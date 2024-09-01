
const exportCampaignProducts = async (campaign_code, object_id) => {
    getExportCampaignProducts(campaign_code).then(async (response) => {
        if (response.length) {
            const XLSX = await import("https://cdn.sheetjs.com/xlsx-0.19.2/package/xlsx.mjs");
            const worksheet = XLSX.utils.json_to_sheet(response);
            const workbook = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(workbook, worksheet, "Campaign Products");
            XLSX.writeFile(workbook, `Campaign_Products_${object_id}.xlsx`, {compression: true});
        }
    }).catch((reason) => {
        console.log(reason);
        alert("Something went wrong!");
    });
};

const exportEmployeeSelection = async (campaign_code, object_id) => {
    getExportCampaignEmployeeSelection(campaign_code).then(async (response) => {
        if (response.length) {
            const XLSX = await import("https://cdn.sheetjs.com/xlsx-0.19.2/package/xlsx.mjs");
            const worksheet = XLSX.utils.json_to_sheet(response);
            const workbook = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(workbook, worksheet, "Campaign Products");
            XLSX.writeFile(workbook, `Campaign_Employee_Selection_${object_id}.xlsx`, {compression: true});
        }
    }).catch((reason) => {
        console.log(reason);
        alert("Something went wrong!");
    });
};
