const BASE_API_URL = '/';

getExportCampaignProducts = async (campaign_code) => {
  return await _callAPI(`campaign/${campaign_code}/campaign-products`, 'GET');
};

getExportCampaignEmployeeSelection = async (campaign_code) => {
  return await _callAPI(`campaign/${campaign_code}/employee-selection`, 'GET');
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