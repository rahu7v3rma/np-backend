function loadJquery() {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = "https://code.jquery.com/jquery-3.7.1.min.js";
      script.integrity = "sha256-/JqT3SQfawRcv/BIHPThkBvs0OEvtFFmqPF/lYI/Cxo="
      script.crossOrigin = 'anonymous'
      script.onload = resolve;
      script.onerror = reject;
      document.body.appendChild(script);
    });
  }

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

document.addEventListener('DOMContentLoaded', () => {
    loadJquery().then(() => {
        $('.dynamic-orderproduct_set').each((idx, el) => {
            const customButton = document.createElement('button');
            customButton.type = 'button';
            customButton.className = 'inline-btn';
            customButton.textContent = 'X';
            el.appendChild(customButton);
            customButton.onclick = () => {
                const purchase_order_product_select = $(customButton.parentNode).find('.field-purchase_order_product>div>select')[0]
                var purchase_order_product_id = purchase_order_product_select.value
                if(purchase_order_product_id) {
                    purchase_order_product_select.value = ''
                    var url = `/logistics/purchase-order-product/${purchase_order_product_id}`;
                    $.ajax({
                        url: url,
                        type: 'DELETE',
                        credentials: 'include',
                        headers: {
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        success: function(data, textStatus, jqXHR) {
                            if (jqXHR.status === 200) {
                               $(`.field-purchase_order_product select option[value="${purchase_order_product_id}"]`).remove();
                                $(purchase_order_product_id).val('');
                            }
                        },
                        error: function(jqXHR, textStatus, errorThrown) {
                            console.error('Delete failed:', errorThrown);
                        }
                    });
                }
            };
        });
    });
}, false);

// Replace the django.jQuery wrapper with a function that waits for django.jQuery
function initializeDjangoAdmin() {
    /**
     * Initialize dynamic behavior for the Django admin “OrderProduct” inlines.
     *
     * Replaces the default django.jQuery wrapper with a self-invoking initializer
     * that:
     *   1. Populates SKU and supplier display cells on initial page load.
     *   2. Updates those cells when the product select input changes.
     *   3. Handles newly added inline rows via the `formset:added` event.
     *
     * Uses the `data-products` JSON payload on each `<select name="*-product_id">`
     * to map product IDs to `{ sku, supplier }` objects, falling back to empty
     * values if the payload or selection is missing.
     *
     * Retries initialization every 100ms until `django.jQuery` is available.
     */
    if (typeof django !== 'undefined' && django.jQuery) {
        django.jQuery(function($) {
            function updateProductInfo(row) {
                var productSelect = row.find('select[name$="-product_id"]');
                var productData = JSON.parse(productSelect.attr('data-products') || '{}');
                var selectedProductId = productSelect.val();
                var productInfo = productData[selectedProductId] || {sku: '', supplier: ''};
                
                // Find the SKU and supplier cells in the same row
                var skuCell = row.find('td.field-sku_display');
                var supplierCell = row.find('td.field-supplier_display');
                
                // Update the values
                skuCell.text(productInfo.sku);
                supplierCell.text(productInfo.supplier);
            }

            // Handle initial load
            $('.dynamic-orderproduct_set').each(function() {
                var row = $(this);
                updateProductInfo(row);
            });

            // Handle product selection changes
            $(document).on('change', 'select[name$="-product_id"]', function() {
                var row = $(this).closest('tr');
                updateProductInfo(row);
            });

            // Handle new inline forms
            $(document).on('formset:added', function(event, $row, formsetName) {
                if (formsetName === 'orderproduct_set') {
                    updateProductInfo($row);
                }
            });
        });
    } else {
        // If django.jQuery is not available yet, try again in a short while
        setTimeout(initializeDjangoAdmin, 100);
    }
}

// Start the initialization process
document.addEventListener('DOMContentLoaded', function() {
    initializeDjangoAdmin();
});
