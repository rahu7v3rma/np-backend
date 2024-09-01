const BASE_API_URL = '/';

export const getProducts = async (
  limit: number,
  page: number,
  organizationId: number,
  priceMin?: number,
  priceMax?: number,
  organizationPriceMin?: number,
  organizationPriceMax?: number,
  brandId?: number,
  supplierId?: number,
  categoryId?: number,
  tagId?: number,
  query?: string,
  productdIds?: number[],
) => {
  const body = {
    page: page,
    limit: limit,
    organization_id: organizationId,
    // below parameters can be undefined, and will not be sent if they are
    price_min: priceMin,
    price_max: priceMax,
    organization_price_min: organizationPriceMin,
    organization_price_max: organizationPriceMax,
    brand_id: brandId,
    supplier_id: supplierId,
    category_id: categoryId,
    tag_id: tagId,
    query,
    product_ids: productdIds,
  };

  return await _callAPI('inventory/product', 'POST', body);
};

export const getCatgoriesSuppliersTags = async () => {
  return await _callAPI('campaign/categories-suppliers-tags', 'GET');
};

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'OPTIONS' | 'HEAD' | 'PATCH';

function _callAPI(
  endpoint: string,
  method: Method = 'GET',
  body?: { [key: string]: string | number | boolean | object | undefined },
  headers?: { [key: string]: string },
) {
  const config: {
    method: string;
    headers: { [key: string]: string };
    body?: string;
  } = {
    method,
    headers: headers || {},
  };

  // for POST requests we need to add the csrf token if there is one
  if (method === 'POST') {
    const csrfTokenInput = document?.querySelector(
      '[name=csrfmiddlewaretoken]',
    );

    if (csrfTokenInput) {
      const csrfToken = (csrfTokenInput as HTMLInputElement).value;
      config['headers']['X-CSRFToken'] = csrfToken;
    }
  }

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
