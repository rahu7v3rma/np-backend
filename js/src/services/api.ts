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
  tagIds?: number[],
  campaignId?: number,
  employeeGroupId?: number,
  product_kind?: string,
  quickOfferId?: number,
  query?: string,
  productdIds?: number[],
  googlePriceMin?: number,
  googlePriceMax?: number,
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
    tag_ids: tagIds,
    campaign_id: campaignId,
    employee_group_id: employeeGroupId,
    product_kind,
    quick_offer_id: quickOfferId,
    query,
    product_ids: productdIds,
    google_price_min: googlePriceMin,
    google_price_max: googlePriceMax,
  };

  return await _callAPI('inventory/product', 'POST', body);
};

export const getCatgoriesSuppliersTags = async () => {
  return await _callAPI('campaign/categories-suppliers-tags', 'GET');
};

export const updateOrganizationProduct = async (
  organizationId: number,
  productId: number,
  price: number,
) => {
  const body = {
    organization: organizationId,
    product: productId,
    price,
  };

  return await _callAPI('campaign/organization-product', 'PUT', body);
};

export const updateEmployeeGroupCampaignProduct = async ({
  productId,
  companyCostPerEmployee,
}: {
  productId: number;
  companyCostPerEmployee: number;
}) => {
  const body = {
    product_id: productId,
    company_cost_per_employee: companyCostPerEmployee,
  };

  return await _callAPI(
    `campaign/employee-group-campaign-product`,
    'PUT',
    body,
  );
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
  if (method === 'POST' || method === 'PUT') {
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
