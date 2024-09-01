let selectedSupplier;
let orderProductsData = []
let selectedOrderId;
const updateViewOrder = (orderProducts, supplierName, orderId) => {
    selectedSupplier = supplierName;
    selectedOrderId = orderId;
    orderProducts.forEach((_prod_data) => {
        orderProductsData = [...orderProductsData, {
            id: _prod_data.prod_id,
            main: _prod_data.prod_image,
            name: _prod_data.product_name,
            category: _prod_data.category,
            brand: _prod_data.brand,
            quantity: _prod_data.quantity_ordered,
            quantity_received: _prod_data.quantity_received,
            sku: _prod_data.sku,
            barcode: _prod_data.barcode,
            cost_price: _prod_data.cost_price,
            status: _prod_data.status,
        }]
    });
    const newRows = orderProducts.reduce((rows, orderProduct) => `
        ${rows}
        <tr class="border-b">
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.sku}
            </td>
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.barcode}
            </td>
            <th scope="row" class="px-6 py-4 font-medium whitespace-nowrap bg-black border-b-white align-middle">
                <div class="flex items-center gap-4">
                    <img height="40" width="40" src="${orderProduct.prod_image}" alt="product image">
                    <span class="whitespace-nowrap overflow-hidden">${orderProduct.product_name}</span>
                </div>
            </th>
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.category}
            </td>
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.brand}
            </td>
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.quantity_ordered}
            </td>
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.quantity_received}
            </td>
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.cost_price * orderProduct.quantity_ordered}
            </td>
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.status}
            </td>
        </tr>
    `, "");

    document.getElementById("table-body").innerHTML = newRows;
}

const updateViewSubtotal = (orderProducts) => {
    if (orderProducts.length) {
        document.getElementById(`sub-total`).innerText = `${orderProducts.reduce((x, _product) => x + _product.quantity_ordered * _product.cost_price, 0)}₪`;
        return
    }
    document.getElementById(`sub-total`).innerText = '0₪';
}

const exportOrder = async () => {
    if (selectedSupplier && orderProductsData.length) {
        const XLSX = await import("https://cdn.sheetjs.com/xlsx-0.19.2/package/xlsx.mjs");

        const orderProductsData_ = [];
        orderProductsData.forEach((_order) => {
            orderProductsData_.push({
                ..._order,
                ...{
                    supplier: selectedSupplier,
                    total_price: (_order.cost_price * _order.quantity),
                }
            })
        });
        const worksheet = XLSX.utils.json_to_sheet(orderProductsData_);
        const workbook = XLSX.utils.book_new();
        const descriptionRow = {
            description: document.getElementById("note").innerHTML,
            total_price: orderProductsData_.reduce((x, _product) => x + _product.total_price, 0),
        }
        XLSX.utils.sheet_add_json(worksheet, [{}], {header: [], skipHeader: true, origin: -1});
        XLSX.utils.sheet_add_json(worksheet, [descriptionRow], {
            header: ["description", "total_price"],
            skipHeader: false,
            origin: -1
        });
        XLSX.utils.book_append_sheet(workbook, worksheet, "Order Products");
        XLSX.writeFile(workbook, `Order_Products_${selectedOrderId}.xlsx`, {compression: true});
    }
};
