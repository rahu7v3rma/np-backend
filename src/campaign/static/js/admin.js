function copyToClipboard(text) {
    var input = document.createElement('input');
    input.setAttribute('value', text);
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    document.body.removeChild(input);
    alert('Link copied to clipboard');
}

$(document).ready(() => {
    const importUrl = './import-employee-group-xlsx/';

    document.getElementById('employee-group-files').click()

    $('#import_employee_group_xlsx').on('click', (event) => {
        event.preventDefault();
        $('#employee-group-files').click();
    })

    $('#employee-group-files').on('change', (event) => {
        event.preventDefault();
        $('#employeegroup_import_form').submit();
    });

    $(document).on('submit', '#employeegroup_import_form', function(event) {
        event.preventDefault();
        const form = $(this);
        const formData = new FormData(this);
        $.ajax({
            url: importUrl,
            type: form.attr('method'),
            data: formData,
            contentType: false,
            processData: false,
            success: function(response) {
                window.location.reload()
            },
            error: function() {
                alert('Failed to import CSV. Please check the file and try again.');
            }
        })
    });
});
