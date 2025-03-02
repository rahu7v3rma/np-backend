import { CheckIcon, PencilIcon, XMarkIcon } from '@heroicons/react/20/solid';
import { Dispatch, SetStateAction, useEffect, useMemo, useState } from 'react';
import { LazyLoadImage } from 'react-lazy-load-image-component';

import { useNPConfig } from '@/contexts/npConfig';
import { updateOrganizationProduct } from '@/services/api';
import { Product } from '@/types/product';

type Props = {
  name: string;
  image?: string;
  brandImage?: string;
  isOutOfStock?: boolean;
  price?: number;
  additionalPrice?: number;
  onClick?: () => void;
  total_cost?: number;
  google_price?: number;
  organization_price?: number;
  value_price?: number;
  voucher_type: string | null;
  discountMode: string;
  handleDiscountModeChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  productKind: string;
  organizationDiscountRate: number;
  handleOrganizationDiscountRateChange: (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => void;
  ordered_quantity?: number;
  id: number;
  setProducts: Dispatch<SetStateAction<Product[]>>;
};

interface ProductPrice {
  label: string;
  value: number | string;
  editable?: boolean;
  alwaysShow?: boolean;
}

export default function ProductCard({
  name,
  image,
  brandImage,
  isOutOfStock = false,
  price = 0,
  additionalPrice = 0,
  onClick,
  total_cost = 0,
  google_price = 0,
  organization_price = 0,
  value_price = 0,
  voucher_type,
  discountMode,
  handleDiscountModeChange,
  productKind,
  organizationDiscountRate,
  handleOrganizationDiscountRateChange,
  ordered_quantity = 0,
  id,
  setProducts,
}: Props) {
  const { config } = useNPConfig();
  const baseSPAAssetsUrl = config?.baseSPAAssetsUrl;
  const organizationId = JSON.parse(
    config?.data.replace(/&quot;/g, '"') || '{}',
  )?.organization_id;

  const [productPrices, setProductPrices] = useState<ProductPrice[]>([]);
  const [editOrganizationPrice, setEditOrganizationPrice] = useState(false);
  const [organizationProductPrice, setOrganizationProductPrice] =
    useState(organization_price);

  useEffect(() => {
    const product_prices: ProductPrice[] = [
      { label: 'EXTRA', value: additionalPrice },
      { label: 'Google Cost', value: google_price },
      { label: 'Organization Price', value: organization_price },
      { label: 'Value', value: value_price },
      { label: 'Total Cost', value: total_cost },
    ];
    if (productKind == 'MONEY') {
      product_prices.push(
        {
          label: "Org'Discount Rate",
          value: organizationDiscountRate,
          editable: true,
          alwaysShow: true,
        },
        {
          label: 'Discount to',
          value: discountMode,
          editable: true,
          alwaysShow: true,
        },
      );
    }
    product_prices.sort((a, b) => {
      if (!a.value && !a.alwaysShow) return -1;
      if (!b.value && !b.alwaysShow) return 1;
      return 0;
    });

    setProductPrices(product_prices);
  }, [
    productKind,
    additionalPrice,
    google_price,
    organization_price,
    value_price,
    total_cost,
    discountMode,
    organizationDiscountRate,
  ]);

  const profit = useMemo(() => {
    return organization_price > 0
      ? +(
          ((organization_price - total_cost) / organization_price) *
          100
        ).toFixed(2)
      : 0;
  }, [organization_price, total_cost]);

  return (
    <div
      className={`relative w-full bg-white shadow-t-lg p-2 rounded-2xl ${onClick ? 'cursor-pointer' : ''}`}
      onClick={onClick}
    >
      <div className="py-[2px] font-semibold">{voucher_type}</div>
      <div className="max-w-full h-auto relative rounded-2xl border">
        <LazyLoadImage
          src={image || `${baseSPAAssetsUrl}default-product.png`}
          alt="product image"
          width={0}
          height={254}
          className="rounded-2xl w-full"
        />

        {isOutOfStock && (
          <div className="top-0 w-full h-full absolute opacity-80 bg-white rounded-2xl">
            <span className="font-medium font-sans h-6 py-0-3 px-2 rounded-lg bg-black text-white text-xs-1 leading-5-1 flex justify-center absolute top-0 items-center left-0">
              OUT OF STOCK
            </span>
          </div>
        )}
      </div>
      <div className="md:px-2">
        <div dir="rtl" className="flex w-full py-2 justify-between">
          <span
            className={`font-medium font-sans text-xs-2 md:text-xs-1 px-1 flex justify-center items-center rounded-lg border border-black leading-5-1 ${price ? '' : 'opacity-0'}`}
          >
            Value ${price}
          </span>
          <div className="w-17 h-5 md:w-20 md:h-6-1">
            <LazyLoadImage
              src={brandImage || `${baseSPAAssetsUrl}default-brand.png`}
              height={22}
              width={80}
              alt="brand image"
            />
          </div>
        </div>
        <p className="font-normal font-sans text-sm">{name}</p>
        {productPrices.map((priceType, priceTypeIndex) => (
          <div className="w-full flex justify-start" key={priceTypeIndex}>
            <span
              className={`flex justify-between items-center mt-2 max-h-9 min-h-6 rounded-xl bg-orange-111 ${!priceType.value && !priceType.alwaysShow && 'opacity-0'}`}
            >
              <span className="max-h-9 min-h-6 rounded-xl block right-2 pr-1 content-center bg-orange-111">
                <p className="font-medium font-sans px-1 text-center text-xs-1 text-orange-112">
                  {priceType.label}
                </p>
              </span>
              {priceType.editable ? (
                priceType.label == 'Discount to' ? (
                  <select
                    value={discountMode}
                    onChange={handleDiscountModeChange}
                    className="w-full border rounded px-2 py-1"
                    style={{ background: 'transparent', border: 'none' }}
                  >
                    <option value="ORGANIZATION">Organization</option>
                    <option value="EMPLOYEE">Employee</option>
                  </select>
                ) : (
                  <div onClick={(e) => e.stopPropagation()}>
                    <input
                      type="number"
                      max={100}
                      min={0}
                      value={organizationDiscountRate || ''}
                      onChange={handleOrganizationDiscountRateChange}
                      className="w-full border rounded px-2 py-1"
                      placeholder="Enter discount rate"
                      style={{ background: 'transparent', border: 'none' }}
                    />
                  </div>
                )
              ) : priceType.label === 'Organization Price' ? (
                <div
                  className="flex items-center"
                  onClick={(event) => {
                    event.stopPropagation();
                  }}
                >
                  {editOrganizationPrice ? (
                    <div className="flex items-center">
                      <input
                        type="number"
                        className="w-[50px]"
                        value={organizationProductPrice}
                        onChange={(event) => {
                          setOrganizationProductPrice(+event.target.value);
                        }}
                      />
                      <div
                        className="cursor-pointer hover:bg-white hover:opacity-50 rounded-full px-1"
                        onClick={() => {
                          if (organizationProductPrice < 0) {
                            alert('Organization price must be greater than 0');
                            return;
                          }
                          if (
                            organizationId &&
                            id &&
                            organizationProductPrice
                          ) {
                            updateOrganizationProduct(
                              organizationId,
                              id,
                              organizationProductPrice,
                            )
                              .then((response) => {
                                if (response?.price) {
                                  setProducts((prevProducts) => {
                                    return prevProducts.map((product) => {
                                      if (product.id === id) {
                                        return {
                                          ...product,
                                          calculated_price: response.price,
                                        };
                                      }
                                      return product;
                                    });
                                  });
                                }
                              })
                              .catch(console.error);
                          }
                          setEditOrganizationPrice(false);
                        }}
                      >
                        <CheckIcon className="size-4" />
                      </div>
                      <div
                        className="cursor-pointer hover:bg-white hover:opacity-50 rounded-full px-1"
                        onClick={() => {
                          setOrganizationProductPrice(organization_price);
                          setEditOrganizationPrice(false);
                        }}
                      >
                        <XMarkIcon className="size-4" />
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center">
                      <label className="font-sans px-1 font-semibold text-base">
                        ${priceType.value}
                      </label>
                      <div
                        className="cursor-pointer hover:bg-white hover:opacity-50 rounded-full px-1"
                        onClick={(event) => {
                          event.stopPropagation();
                          setEditOrganizationPrice(true);
                        }}
                      >
                        <PencilIcon className="size-3" />
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <label className="font-sans px-1 font-semibold text-base">
                  ${priceType.value}
                </label>
              )}
            </span>
          </div>
        ))}
        <div className="w-full flex justify-start">
          <span className="flex justify-between items-center mt-2 max-h-9 min-h-6 rounded-xl bg-orange-111">
            <span className="max-h-9 min-h-6 rounded-xl block right-2 pr-1 content-center bg-orange-111">
              <p className="font-medium font-sans px-1 text-center text-xs-1 text-orange-112">
                Profit
              </p>
            </span>
            <label className="font-sans px-1 font-semibold text-base">
              {`${profit}%`}
            </label>
          </span>
        </div>
        {ordered_quantity > 0 && (
          <div className="w-full flex justify-start">
            <span
              className={`flex justify-between items-center mt-2 max-h-9 min-h-6 rounded-xl bg-orange-111`}
            >
              <span className="max-h-9 min-h-6 rounded-xl block right-2 pr-1 content-center bg-orange-111">
                <p className="font-medium font-sans px-1 text-center text-xs-1 text-orange-112">
                  Ordered Quantity
                </p>
              </span>
              <label className="font-sans px-1 font-semibold text-base">
                {ordered_quantity}
              </label>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
