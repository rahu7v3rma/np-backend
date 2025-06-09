import { Checkbox } from '@headlessui/react';
import { CheckIcon, PencilIcon, XMarkIcon } from '@heroicons/react/20/solid';
import {
  Dispatch,
  SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { LazyLoadImage } from 'react-lazy-load-image-component';

import { useNPConfig } from '@/contexts/npConfig';
import { updateEmployeeGroupCampaignProduct } from '@/services/api';
import { Product } from '@/types/product';

const formatWord = (word: string) => {
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
};

interface EditablePriceComponentProps {
  value: number | string;
  label: string;
  onSave: (newValue: number | string) => void;
  notEditable?: boolean;
}

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
  _handleDiscountModeChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  productKind: string;
  handleValueChange: (product_id: number, value: number) => void;
  handleProductCompanyCostChange?: (productId: number, newCost: number) => void;
  ordered_quantity?: number;
  id: number;
  _setProducts: Dispatch<SetStateAction<Product[]>>;
  onProductClick: (product_id: number, selected: boolean) => void;
  is_selected?: boolean;
};

interface ProductPrice {
  label: string;
  value: number | string;
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
  _handleDiscountModeChange,
  productKind,
  handleValueChange,
  handleProductCompanyCostChange,
  ordered_quantity = 0,
  id,
  _setProducts,
  onProductClick,
  is_selected = false,
}: Props) {
  const { config } = useNPConfig();
  const baseSPAAssetsUrl = config?.baseSPAAssetsUrl;
  const configData = JSON.parse(config?.data.replace(/&quot;/g, '"') || '{}');
  const organizationId = configData?.organization_id;
  const status = configData?.campaign_status;
  const [productPrices, setProductPrices] = useState<ProductPrice[]>([]);
  const [selected, setSelected] = useState<boolean>(false);

  useEffect(() => {
    setSelected(is_selected);
  }, [is_selected]);

  useEffect(() => {
    const product_prices: ProductPrice[] = [
      { label: 'EXTRA', value: additionalPrice },
      { label: 'Google Cost', value: google_price },
      { label: 'Company Cost Per Employee', value: organization_price },
      { label: 'Discount to', value: 'Employee', alwaysShow: true },
      { label: 'Value', value: value_price },
      { label: 'Total Cost', value: total_cost },
    ];

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
    status,
  ]);

  const profit = useMemo(() => {
    return organization_price > 0
      ? +(
          ((organization_price - total_cost) / organization_price) *
          100
        ).toFixed(2)
      : 0;
  }, [organization_price, total_cost]);

  const handleCheckboxChange = useCallback(
    (productSelected: boolean) => {
      setSelected(productSelected);
      onProductClick(id, productSelected);
    },
    [onProductClick, id],
  );

  return (
    <div
      className={`relative w-full bg-white shadow-t-lg p-2 rounded-2xl ${onClick ? 'cursor-pointer' : ''}`}
      onClick={onClick}
    >
      <Checkbox
        checked={selected}
        onChange={handleCheckboxChange}
        className="group block size-12 rounded-lg border bg-white data-[checked]:bg-blue-500 absolute right-2 top-1 z-50"
      >
        {/* Checkmark icon */}
        <svg
          className={`stroke-white opacity-0 ${selected ? 'opacity-100' : ''}`}
          viewBox="0 0 14 14"
          fill="none"
        >
          <path
            d="M3 8L6 11L11 3.5"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </Checkbox>
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
              {['Company Cost Per Employee', 'Value'].includes(
                priceType.label,
              ) ? (
                <EditablePriceComponent
                  label={priceType.label}
                  value={priceType.value}
                  notEditable={
                    (priceType.label === 'Value' &&
                      discountMode !== 'EMPLOYEE') ||
                    status === 'ACTIVE'
                  }
                  onSave={(value: number | string) => {
                    if (priceType.label === 'Company Cost Per Employee') {
                      const numValue =
                        typeof value === 'string' ? parseFloat(value) : value;
                      if (organizationId && id && numValue) {
                        updateEmployeeGroupCampaignProduct({
                          productId: id,
                          companyCostPerEmployee: numValue,
                        });
                        handleProductCompanyCostChange?.(id, numValue);
                      }
                    } else {
                      const numValue =
                        typeof value === 'string' ? parseFloat(value) : value;
                      handleValueChange(id, numValue);
                    }
                  }}
                />
              ) : (
                <label className="font-sans px-1 font-semibold text-base">
                  {typeof priceType.value === 'string'
                    ? formatWord(priceType.value)
                    : priceType.value}
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

const EditablePriceComponent = ({
  value,
  label,
  onSave,
  notEditable = false,
}: EditablePriceComponentProps) => {
  const { config } = useNPConfig();
  const configData = JSON.parse(config?.data.replace(/&quot;/g, '"') || '{}');
  const status = configData?.status;
  const [isEdit, setIsEdit] = useState(false);
  const [newValue, setNewValue] = useState(value);

  useEffect(() => {
    setNewValue(value);
  }, [value]);

  const isEditable = !notEditable && status !== 'ACTIVE';

  return (
    <div
      className="flex items-center"
      onClick={(event) => {
        event.stopPropagation();
      }}
    >
      {isEdit && isEditable ? (
        <div className="flex items-center">
          <input
            type="number"
            className="w-[50px]"
            value={newValue}
            onChange={(event) => {
              setNewValue(+event.target.value);
            }}
          />
          <div
            className="cursor-pointer hover:bg-white hover:opacity-50 rounded-full px-1"
            onClick={() => {
              const numValue =
                typeof newValue === 'string' ? parseFloat(newValue) : newValue;
              if (numValue < 0) {
                alert(`${label} must be greater than 0`);
                return;
              }
              onSave(newValue);
              setIsEdit(false);
            }}
          >
            <CheckIcon className="size-4" />
          </div>
          <div
            className="cursor-pointer hover:bg-white hover:opacity-50 rounded-full px-1"
            onClick={() => {
              setNewValue(value);
              setIsEdit(false);
            }}
          >
            <XMarkIcon className="size-4" />
          </div>
        </div>
      ) : (
        <div className="flex items-center">
          <label className="font-sans px-1 font-semibold text-base">
            ${newValue}
          </label>
          <div
            className="cursor-pointer hover:bg-white hover:opacity-50 rounded-full px-1"
            onClick={(event) => {
              event.stopPropagation();
              if (isEditable) {
                setIsEdit(true);
              }
            }}
          >
            {isEditable && <PencilIcon className="size-3" />}
          </div>
        </div>
      )}
    </div>
  );
};
