const BASE_API_URL = '/';

getCookie = (name) => {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
}

getCatgoriesSuppliersTags = async () => {
  return await _callAPI('campaign/categories-suppliers-tags', 'GET');
};

getSuppliers = async () => {
  return await _callAPI('inventory/suppliers', 'GET');
};

getProductsBySupplier = async ({
  name,
}) => {
  return await _callAPI(
    `inventory/supplier-products?name=${encodeURIComponent(name)}`,
    'GET',
  );
};

sendApprovedPO = async (id) => {
    const response = await _callAPI(`logistics/order-products-status/${id}`, 'PATCH', {}, {
        'X-CSRFToken': getCookie("csrftoken"),
    });
    
    // Return the response for better error handling in the calling function
    return response;
};

sendProductsOrder = async (order, id) => {
    if (id !== "") {
        return await _callAPI(`logistics/order-products/${id}`, 'PATCH', order, {
            'X-CSRFToken': getCookie("csrftoken"),
        });
    }
    return await _callAPI(`logistics/order-products`, 'POST', order, {
        'X-CSRFToken': getCookie("csrftoken"),
    });
};

function _callAPI(
  endpoint,
  method = 'GET',
  body,
  headers,
) {
  const config = {
    method,
    headers: headers || {},
  };

  if (body) {
    config['headers']['Content-Type'] = 'application/json';
    config['body'] = JSON.stringify(body);
  }

  return fetch(BASE_API_URL + endpoint, config)
    .catch((_err) => {
      // reject with unknown error
      return Promise.reject({
        status: -1,
      });
    })
    .then((response) =>
      response
        .json()
        .catch((_err) => {
          return Promise.reject({ status: response.status });
        })
        .then((responseBody) => {
          if (response.ok) {
            return Promise.resolve(responseBody.data);
          } else {
            // error and description may not be available
            return Promise.reject({
              status: response.status,
              data: responseBody,
            });
          }
        }),
    );
}
