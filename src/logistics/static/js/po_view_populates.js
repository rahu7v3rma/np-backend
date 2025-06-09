let selectedSupplier;
let orderProductsData = [];
let selectedOrderId;
const updateViewOrder = (orderProducts, supplierName, orderId , hasMoneyProducts) => {
  const voucherHeader = document.getElementById("voucherValueHeader");
  const discountHeader = document.getElementById("supplierDiscountHeader");
  if (hasMoneyProducts) {
    voucherHeader.style.display = "table-cell";
    discountHeader.style.display = "table-cell";
} else {
    voucherHeader.style.display = "none";
    discountHeader.style.display = "none";
}
  selectedSupplier = supplierName;
  selectedOrderId = orderId;
  orderProducts.forEach((_prod_data) => {
    orderProductsData = [
      ...orderProductsData,
      {
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
        voucher_value: _prod_data.voucher_value,
        supplier_discount_rate: _prod_data.supplier_discount_rate,
        product_kind: _prod_data.product_kind
      },
    ];
  });
  const newRows = orderProducts.reduce(
    (rows, orderProduct) => `
        ${rows}
        <tr class="border-b">
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.sku}${orderProduct.variations}
            </td>
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.barcode}
            </td>
            <th scope="row" class="px-6 py-4 font-medium whitespace-nowrap bg-black border-b-white align-middle">
                <div class="flex items-center gap-4">
                    <img height="40" width="40" src="${
                      orderProduct.prod_image
                    }" alt="product image">
                    <span class="whitespace-nowrap overflow-hidden cursor-pointer" onclick="window.open('/admin/campaign/order/?purchase_order=${selectedOrderId}')">${
      orderProduct.product_name
    }</span>
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
            <td class="text-center py-4 bg-black border-b-white align-middle">
                ${orderProduct.product_kind}
            </td>
            ${hasMoneyProducts ? `
            <td class="text-center py-4 bg-black border-b-white align-middle">${orderProduct.voucher_value ? `₪${orderProduct.voucher_value}` : ''}</td>
            <td class="text-center py-4 bg-black border-b-white align-middle">${orderProduct.supplier_discount_rate ? `${orderProduct.supplier_discount_rate}%` : ''}</td>` : ''}

            
        </tr>
    `,
    ""
  );

  document.getElementById("table-body").innerHTML = newRows;
};

const updateViewSubtotal = (orderProducts) => {
  if (orderProducts.length) {
    document.getElementById(`sub-total`).innerText = `${orderProducts.reduce(
      (x, _product) => x + _product.quantity_ordered * _product.cost_price,
      0
    )}₪`;
    return;
  }
  document.getElementById(`sub-total`).innerText = "0₪";
};

const exportOrder = async () => {
  if (selectedSupplier && orderProductsData.length) {
    const searchParams = new URLSearchParams(window.location.search);
    searchParams.set("export", "1");
    window.location.replace(
      `${window.location.pathname}?${searchParams.toString()}`
    );
  }
};
