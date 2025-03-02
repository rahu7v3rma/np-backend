let products;
let selectedSupplier;
let selectedProduct;
let selectedProductQuantity;
let orderProducts = [];
let suppliers;
let order;
let selectedOrderStatus;

function decodeHTMLEntities(text) {
    var textArea = document.createElement('textarea');
    textArea.innerHTML = text;
    return textArea.value;
  }

const roundValue = (value) => Math.round(value * 100) / 100;

const suppliersOrder = async (supplier_name = "", selected_product_ids=[], note = "", poNumber = "", orderStatus = "", variations = None) => {
    const variations_mapping = JSON.parse(decodeHTMLEntities(variations || '{}').replaceAll("'", '"'));
    try {
        selectedOrderStatus = orderStatus;
        document.getElementById("po-number").innerText = poNumber ? `PO NUMBER ${poNumber}` : 'NEW PO';

        suppliers = await getSuppliers();
        suppliers.sort((a, b) => a.name < b.name ? -1 : 1);

        const newOptions = suppliers.reduce(
            (x, supplier) => `${x}<option value="${supplier.name}">${supplier.name}</option>`, "<option value=\"active\">Supplier</option>"
        );
        document.getElementById("suppliers").innerHTML = newOptions;
        selectedProductQuantity = 1

        if (supplier_name !== "") {
            document.getElementById("suppliers").value = supplier_name
            selectedSupplier = suppliers.find((supplier) => supplier.name === supplier_name);
            await populateProducts(selectedSupplier);
            selected_product_ids.forEach((_prod_data) => {
                selectedProduct = {...products.find((product) => product.id === _prod_data[0])};
                selectedProduct['sku'] = variations_mapping[`${_prod_data[2]}`] ? `${selectedProduct['sku']}${variations_mapping[`${_prod_data[2]}`]}` : selectedProduct['sku'] 
                selectedProductQuantity = _prod_data[1]
                addProduct();
                selectedProductQuantity = 1
            });
            document.getElementById("note").innerHTML = note
        }

        document.getElementById("suppliers").addEventListener("change", async (event) => {
            selectedSupplier = suppliers.find((supplier) => supplier.name === event.target.value);
            await populateProducts(selectedSupplier);
        }, false);
        document.getElementById("products").addEventListener("change", async (event) => {
                selectedProduct = products.find((product) => product.id === Number(event.target.value));
            }, false
        );
    } catch (error) {
        alert('someting went wrong!');
    }
    await loadOrderFromUrl();
};

const loadOrderFromUrl = async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const sku_variations = {};
    const urlSupplierName = urlParams.get('supplierName');
    const urlProductSkus = urlParams.get('productSkus')?.split(',').reduce((res, ps) => {
        const splitProduct = ps.split('|||');
        const sku = splitProduct[0];
        if (!Object.keys(sku_variations).includes(sku)){
            sku_variations[sku] = []
        }
        const quantity = splitProduct.length > 1 ? Math.max(1, Number.parseInt(splitProduct[1]) || 1) : 1;
        sku_variations[sku].push({
            quantity: quantity,
            variation: splitProduct[2],
            order: splitProduct[3],
        });

        return { ...res, [sku]: quantity };
    }, {});

    if (urlSupplierName && urlProductSkus) {
        selectedSupplier = suppliers.filter(x => x.name == urlSupplierName).map(x => ({
            id: x.id,
            name: x.name,
            email: x.email
        }))[0];
        document.querySelector(`#suppliers option[value="${selectedSupplier.name}`).selected = true;

        await populateProducts({name: selectedSupplier.name});
        orderProducts = products.filter(x => x.sku in urlProductSkus).map((selectedProduct) => {
            const productData = {
                id: selectedProduct.id,
                main: selectedProduct.main_image_link,
                name: selectedProduct.name,
                category: selectedProduct.category,
                brand: selectedProduct.brand.name,
                quantity: 0,
                quantity_received: 0,
                sku: selectedProduct.sku,
                barcode: selectedProduct.reference,
                cost_price: roundValue(selectedProduct.cost_price * (1 - selectedProduct.tax_percent / 100)),
                product_kind: selectedProduct.product_kind,
                status: selectedOrderStatus,
            };
            if (selectedProduct.product_kind === "MONEY") {
                productData.voucher_value = selectedProduct.client_discount_rate || 0;
                productData.supplier_discount_rate = selectedProduct.supplier_discount_rate || 0;
            }

            return productData;
        });
        orderProducts = orderProducts.map(product => sku_variations[product.sku].map((variation) => (
        {...product, ...{
            quantity: variation.quantity,
            sku: variation.variation,
            order: variation.order
        }}))).flat();
        orderProducts.sort((a, b) => a.sku < b.sku ? -1 : 1);
        const hasMoneyProducts = orderProducts.some(product => product.product_kind === "MONEY");

        updateOrder(hasMoneyProducts);
        updateSubtotal();
    }
};

const populateProducts = async (supplier) => {
    try {
        if (!supplier) {
            products = [];
            selectedProduct = undefined;
            orderProducts = [];
            updateOrder();
        } else {
            products = await getProductsBySupplier(supplier);
        }
        let newOptions = products.reduce((x, product) => `${x}<option value=${product.id}>${product.sku}/${product.name}</option>`, "<option value=\"0\">Sku/Name</option>");
        document.getElementById("products").innerHTML = newOptions;
    } catch (error) {
        alert('someting went wrong!');
    }
};

const addProduct = () => {
    if (selectedProduct && !orderProducts.find((_product) => _product.sku === selectedProduct.sku)) {
        let newProduct = {
            id: selectedProduct.id,
            main: selectedProduct.main_image_link,
            name: selectedProduct.name,
            category: selectedProduct.category,
            brand: selectedProduct.brand.name,
            quantity: selectedProductQuantity,
            quantity_received: 0,
            sku: selectedProduct.sku,
            barcode: selectedProduct.reference,
            cost_price: roundValue(selectedProduct.cost_price * (1 - selectedProduct.tax_percent / 100)),
            product_kind: selectedProduct.product_kind,
            status: selectedOrderStatus,
        }
        if (selectedProduct.product_kind == 'MONEY') {
            newProduct.voucher_value = selectedProduct.client_discount_rate;
            newProduct.supplier_discount_rate = selectedProduct.supplier_discount_rate;
        }
        orderProducts = [...orderProducts, newProduct];
        const hasMoneyProducts = orderProducts.some(product => product.product_kind === "MONEY");
        updateOrder(hasMoneyProducts);
        updateSubtotal();
    }
};

const updateOrder = (hasMoneyProducts) => {
    // Show or hide the "Voucher Value" and "Supplier Discount Rate" headers
    const voucherHeader = document.getElementById("voucherValueHeader");
    const discountHeader = document.getElementById("supplierDiscountHeader");

    // If there are money products, show the headers
    if (hasMoneyProducts) {
        voucherHeader.style.display = "table-cell";
        discountHeader.style.display = "table-cell";
    } else {
        voucherHeader.style.display = "none";
        discountHeader.style.display = "none";
    }

    // Render the table rows
    const newRows = orderProducts.reduce((x, orderProduct) => `
        ${x} <tr class="border-b">
        <td class="text-center py-4 bg-black border-b-white align-middle">${orderProduct.sku}</td>
        <td class="text-center py-4 bg-black border-b-white align-middle">${orderProduct.barcode}</td>
        <th scope="row"
          class="px-6 py-4 font-medium whitespace-nowrap bg-black border-b-white align-middle">
          <div class="flex items-center gap-4"><img height="40" width="40" src="${orderProduct.main}" alt="product image"><span
              class="whitespace-nowrap overflow-hidden cursor-pointer" onclick="window.open('/admin/campaign/order/?product_id=${orderProduct.id}')">${orderProduct.name}</span></div>
        </th>
        <th scope="row"
            class="px-6 py-4 font-medium whitespace-nowrap bg-black border-b-white align-middle">
                ${orderProduct.product_kind}
        </th>
        ${hasMoneyProducts ? `
            <td class="text-center py-4 bg-black border-b-white align-middle">${orderProduct.voucher_value ? `₪${orderProduct.voucher_value}` : ''}</td>
            <td class="text-center py-4 bg-black border-b-white align-middle">${orderProduct.supplier_discount_rate ? `₪${orderProduct.supplier_discount_rate}` : ''}</td>` : ''}

        <td class="text-center py-4 bg-black border-b-white align-middle">₪${orderProduct.cost_price}</td>
        <td class="py-4 bg-black border-b-white align-middle">
          <div
            class="flex mx-auto w-[78px] h-[22px] rounded-lg px-2 bg-[#F2F4F8] justify-between items-center">
            <button onclick="updateQuantity(${orderProduct.id}, '${orderProduct.sku}', -1)" class="w-[20px] h-[20px]"><svg stroke="currentColor" fill="currentColor"
                stroke-width="0" viewBox="0 0 448 512" class="w-[10px] h-[10px] mx-auto" height="1em"
                width="1em" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M432 256c0 17.7-14.3 32-32 32L48 288c-17.7 0-32-14.3-32-32s14.3-32 32-32l352 0c17.7 0 32 14.3 32 32z">
                </path>
              </svg></button><label class="m-auto" id="quantity-${orderProduct.id}">${orderProduct.quantity}</label><button onclick="updateQuantity(${orderProduct.id}, '${orderProduct.sku}', 1)" class="w-[20px] h-[20px]"><svg
                stroke="currentColor" fill="currentColor" stroke-width="0" viewBox="0 0 448 512"
                class="w-[10px] h-[10px] mx-auto" height="1em" width="1em"
                xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M256 80c0-17.7-14.3-32-32-32s-32 14.3-32 32V224H48c-17.7 0-32 14.3-32 32s14.3 32 32 32H192V432c0 17.7 14.3 32 32 32s32-14.3 32-32V288H400c17.7 0 32-14.3 32-32s-14.3-32-32-32H256V80z">
                </path>
              </svg></button>
          </div>
        </td>
        <td class="text-center py-4 bg-black border-b-white align-middle" id="total-${orderProduct.id}">₪${roundValue(orderProduct.cost_price * orderProduct.quantity)}</td>
        <td class="text-center py-4 bg-black border-b-white align-middle"><button class="h-full w-10" onclick="deleteProduct('${orderProduct.sku}')"
            type="button" data-headlessui-state=""><img
              src="/static/svgs/trash.svg" height="16" width="16"
              alt="trash image"></button></td>
      </tr>
    `, "");
    document.getElementById("table-body").innerHTML = newRows;
};

const updateQuantity = (idx, sku, quantity) => {
    let orderProduct = orderProducts.find((_product) => String(_product.sku) === String(sku));
    if (orderProduct) {
        let newQuantity = orderProduct.quantity + quantity;
        if (newQuantity > 0) {
            orderProduct.quantity = newQuantity;
            document.getElementById(`quantity-${idx}`).innerText = newQuantity;
            document.getElementById(`total-${idx}`).innerText = `₪${roundValue(orderProduct.cost_price * newQuantity)}`;
        }
    }
    const hasMoneyProducts = orderProducts.some(product => product.product_kind === "MONEY");
    updateOrder(hasMoneyProducts);
    updateSubtotal();
};

const deleteProduct = (sku) => {
    orderProducts = orderProducts.filter((_product) => _product.sku !== sku);
    const hasMoneyProducts = orderProducts.some(product => product.product_kind === "MONEY");
    updateOrder(hasMoneyProducts);
    updateSubtotal();
};

const updateSubtotal = () => {
    if (orderProducts.length) {
        document.getElementById(`sub-total`).innerText = `${roundValue(orderProducts.reduce((x, _product) => x + _product.quantity * _product.cost_price, 0))}₪`;
        return
    }
    document.getElementById(`sub-total`).innerText = '0₪';
};

const savePO =
    async (
      status,
      id = null,
      keepEdit = true,
    ) => {
        if (orderProducts.length && selectedSupplier) {
            const note = document.getElementById(`note`).value.trim();
            const data = {
                supplier: selectedSupplier.id,
                notes: note,
                status: status,
                products: orderProducts.map((product) => ({
                    product_id: product.id,
                    quantity_ordered: product.quantity,
                    quantity_sent_to_logistics_center: 0,
                    order: product.order
                })),
            };

            // approved status is not set directly, so unset this change in the
            // payload
            if (status === 'APPROVED') {
                data.status = selectedOrderStatus;
            }

            try {
                const response = await sendProductsOrder(data, id);
                if (status === 'SENT_TO_SUPPLIER') {
                    document.getElementById("po-number").innerText = `PO NUMBER ${id}`;
                    orderProducts = [];
                    updateOrder();
                    updateSubtotal();
                    window.location.href = '/admin/logistics/poorder/';
                    return;
                } else if (status === 'APPROVED') {
                    await sendApprovedPO(id);
                }

                if (!keepEdit) {
                    window.location.href = '/admin/logistics/poorder/';
                } else {
                    window.location.href = `/admin/logistics/poorder/${response.id}/change/`;
                }
            } catch (ex) {
                if (ex?.status === 400 && ex.data?.message) {
                    alert(`Error: ${ex.data.message}`);
                } else {
                    alert('something went wrong!');
                }
            }
        }
    };

const sendPO = (id) => {
    if (!selectedSupplier?.email) {
        alert('PO cannot be sent since the supplier does not have an email address set')
    } else {
        savePO('SENT_TO_SUPPLIER', id, true)
    }
};

const exportOrder = async () => {
    if (selectedSupplier && orderProducts.length) {
        const searchParams = new URLSearchParams(window.location.search);
        searchParams.set('export','1');
        window.location.replace(`${window.location.pathname}?${searchParams.toString()}`)
    }
};

const importOrderProducts = async (event) => {
    const XLSX = await import("https://cdn.sheetjs.com/xlsx-0.19.2/package/xlsx.mjs");
    const file = event.files[0];
    const reader = new FileReader();

    reader.readAsArrayBuffer(file);
    reader.onload = (e) => {

        try {
            const binaryStr = new Uint8Array(e.target.result);
            const wb = XLSX.read(binaryStr, {type: 'array', raw: true, cellFormula: false});
            const wsName = wb.SheetNames[0];
            const data = XLSX.utils.sheet_to_json(wb.Sheets[wsName]);
            if (!data.length) return;
            let supplier_name = null;
            let find_duplicate_supplier;

            const lastRow = data[data.length - 1];
            if (lastRow.id) {
                document.getElementById("note").innerHTML = lastRow.id;
            }

            for (const _prod_data of data) {
                if (supplier_name === null) {
                    supplier_name = _prod_data.supplier;
                } else if (_prod_data.supplier && supplier_name !== _prod_data.supplier) {
                    find_duplicate_supplier = true;
                    break;
                }
            }

            if (find_duplicate_supplier) {
                alert("Multiple suppliers are not allowed to enter");
                return;
            }
            const selectedSupplierImport = suppliers.find((supplier) => supplier.name === supplier_name);
            if (!selectedSupplierImport) {
                alert("supplier doesn't exist!");
                return;
            }
            selectedSupplier = selectedSupplierImport
            document.getElementById("suppliers").value = selectedSupplierImport.name
            populateProducts(selectedSupplierImport).then(() => {
                let skusSet = new Set(products.map(prod => prod.sku));
                let products_data = data.filter(prod => skusSet.has(prod.sku));
                let orderProductsMap = new Map();
                orderProducts.forEach(prod => {
                    orderProductsMap.set(prod.sku, prod);
                });
                products_data.forEach(newProd => {
                    if (orderProductsMap.has(newProd.sku)) {
                        let existingProd = orderProductsMap.get(newProd.sku);
                        existingProd.quantity = newProd.quantity;
                    } else {
                        orderProductsMap.set(newProd.sku, newProd);
                    }
                });
                orderProducts = Array.from(orderProductsMap.values());
                const hasMoneyProducts = orderProducts.some(product => product.product_kind === "MONEY");
                updateOrder(hasMoneyProducts);
                updateSubtotal();
            })
        } catch {
            alert("an error occurred while importing the order");
        }
    }
    document.getElementById("order-files").value = null;
};
