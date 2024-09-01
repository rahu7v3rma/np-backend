import { useState, useEffect } from 'react';
import { LazyLoadImage } from 'react-lazy-load-image-component';

import { useNPConfig } from '@/contexts/npConfig';

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
};

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
}: Props) {
  const { config } = useNPConfig();
  const baseSPAAssetsUrl = config?.baseSPAAssetsUrl;

  const [productPrices, setProductPrices] = useState<
    { label: string; value: number }[]
  >([]);

  useEffect(() => {
    const product_prices = [
      { label: 'EXTRA', value: additionalPrice },
      { label: 'Google Cost', value: google_price },
      { label: 'Organization Price', value: organization_price },
      { label: 'Total Cost', value: total_cost },
    ];

    product_prices.sort((a, b) => {
      if (!a.value) return -1;
      if (!b.value) return 1;
      return 0;
    });

    setProductPrices(product_prices);
  }, [additionalPrice, google_price, organization_price, total_cost]);

  return (
    <div
      className={`relative w-full bg-white shadow-t-lg p-2 rounded-2xl ${onClick ? 'cursor-pointer' : ''}`}
      onClick={onClick}
    >
      <div className="max-w-full h-auto relative rounded-2xl">
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
              className={`flex justify-between items-center mt-2 max-h-9 min-h-6 rounded-xl bg-orange-111 ${!priceType.value && 'opacity-0'}`}
            >
              <span className="max-h-9 min-h-6 rounded-xl block right-2 pr-1 content-center bg-orange-111">
                <p className="font-medium font-sans px-1 text-center text-xs-1 text-orange-112">
                  {priceType.label}
                </p>
              </span>
              <label className="font-sans px-1 font-semibold text-base">
                ${priceType.value}
              </label>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
