function checkAll() {
    var checkBox = document.getElementById("option-all");
    document.querySelectorAll("input[type=checkbox]").forEach(
        (option) => option.checked=checkBox.checked
    );
  }

exportXLSX = () => {
    const rows = [...$('table tbody tr')
        .filter((i, e)=>$(e).find('input[type="checkbox"]').prop('checked'))
        .map((i,e)=>
            ({
                supplier: $(e).find('#supplier_name').text(),
                brand: $(e).find('#brand_name').text(),
                sku: $(e).find('#sku').text(),
                reference: $(e).find('#reference').text(),
                total: $(e).find('#total').text(),
                price: $(e).find('#price').text(),
            })
        )]
    const worksheet = XLSX.utils.json_to_sheet(rows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Sheet1');
    XLSX.writeFile(workbook, 'PO_Summary.xlsx');
}

$(document).ready(()=>{
    $('input[type="checkbox"]').change(function(){
        if($(':checked').length){
            $('#exportXLSX').removeAttr('disabled');
        } else {
            $('#exportXLSX').prop('disabled', true);
        }
    });
    $('tbody input[type="checkbox"]').change(function(){
        const checkedSupplierName = $('tbody input:checked').map(function(){
            return $(this).parents('tr').find('td[id="supplier_name"]').text();
        }).get()[0];
        if(checkedSupplierName!==$(this).parents('tr').find('td[id="supplier_name"]').text()){
            $(this).prop('checked', false);
        }

        if(checkedSupplierName){
            $('#createPO').removeAttr('disabled');

        } else {
            $('#createPO').prop('disabled', true);
        }
    });
});

createPO = () => {
    const supplierName = $('tbody input:checked').map(function(){
        return $(this).parents('tr').find('td[id="supplier_name"]').text();
    }).get()[0];
    const productSkus = $('tbody input:checked').map(function(){
        return $(this).parents('tr').find('td[id="sku"]').text();
    }).get();
    
    window.open(`/admin/logistics/poorder/add/?supplierName=${supplierName}&productSkus=${productSkus.join()}`, '_blank');
}