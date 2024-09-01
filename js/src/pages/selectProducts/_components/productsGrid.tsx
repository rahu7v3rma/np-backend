import { useCallback, useEffect, useRef, useState } from 'react';

import { useNPConfig } from '@/contexts/npConfig';
import { getProducts } from '@/services/api';
import { Product } from '@/types/product';

import useViewportEntry from '../_hooks/useViewportEntry';

import Filter from './filter';
import Loader from './loader';
import ProductCard from './productCard';
import SelectionContainer from './selectionContainer';

interface Props {
  formId: number;
  organizationId: number;
  budget: number;
}

const ProductComponent = ({ formId, organizationId, budget }: Props) => {
  const { config } = useNPConfig();
  const currentWizardStep = config?.currentWizardStep || '-1';

  const [loading, setLoading] = useState<boolean>(true);
  const [queryParams, setQueryParams] = useState<{
    page: number;
    priceMin?: number;
    priceMax?: number;
    organizationPriceMin?: number;
    organizationPriceMax?: number;
    brandId?: number;
    supplierId?: number;
    categoryId?: number;
    tagId?: number;
    query?: string;
    selectedProductsIds?: number[];
  }>({ page: 1 });
  const [products, setProducts] = useState<Product[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [selectedProductIds, setSelectedProductIds] = useState<number[]>([]);

  const gridEndRef = useRef<HTMLDivElement>(null);
  const baseSPAAssetsUrl = config?.baseSPAAssetsUrl;

  useEffect(() => {
    if (config?.data !== '{}') {
      const productIds = JSON.parse(
        config?.data.replace(/&quot;/g, '"') || '{}',
      )?.products?.[formId];

      if (productIds) {
        setSelectedProductIds(productIds);
      }
    }
  }, [config, formId]);

  const fetchProducts = useCallback(async () => {
    setLoading(true);

    try {
      const productsPage: {
        page_data: Product[];
        has_more: boolean;
      } = await getProducts(
        10,
        queryParams.page,
        organizationId,
        queryParams.priceMin,
        queryParams.priceMax,
        queryParams.organizationPriceMin,
        queryParams.organizationPriceMax,
        queryParams.brandId,
        queryParams.supplierId,
        queryParams.categoryId,
        queryParams.tagId,
        queryParams.query,
        queryParams.selectedProductsIds,
      );

      // sort each product's images array so that the main image is first
      for (const product of productsPage.page_data as Product[]) {
        product.images?.sort((a, b) => Number(b?.main) - Number(a?.main));
      }

      setProducts((prevProducts) => {
        if (queryParams.page === 1) {
          return productsPage.page_data;
        }
        return [...prevProducts, ...productsPage.page_data];
      });
      setHasMore(productsPage.has_more);
    } catch (error) {
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }, [queryParams, organizationId]);

  useEffect(() => {
    // fetch products on page mount
    fetchProducts();
  }, [fetchProducts]);

  const onProductClick = useCallback(
    (productId: number) => {
      if (selectedProductIds.includes(productId)) {
        setSelectedProductIds(
          selectedProductIds.filter((id) => id !== productId),
        );
      } else {
        setSelectedProductIds([...selectedProductIds, productId]);
      }
    },
    [selectedProductIds],
  );

  const handleRemoveProduct = useCallback(
    (productId: number) => {
      setSelectedProductIds(
        selectedProductIds.filter((id) => id !== productId),
      );
    },
    [selectedProductIds],
  );

  const handleApplyFilter = useCallback(
    (
      priceMin?: number,
      priceMax?: number,
      organizationPriceMin?: number,
      organizationPriceMax?: number,
      brandId?: number,
      supplierId?: number,
      categoryId?: number,
      tagId?: number,
      query?: string,
      selectedProducts?: boolean,
    ) => {
      setQueryParams({
        priceMin,
        priceMax,
        organizationPriceMin,
        organizationPriceMax,
        brandId,
        supplierId,
        categoryId,
        tagId,
        query,
        selectedProductsIds: selectedProducts ? selectedProductIds : undefined,
        page: 1,
      });
    },
    [selectedProductIds],
  );

  const handleGridScrolledToEnd = useCallback(() => {
    if (hasMore && !loading) {
      setQueryParams((prevParams) => ({
        ...prevParams,
        page: prevParams.page + 1,
      }));
    }
  }, [hasMore, loading]);

  // "subscribe" to events of the component at the end of the products grid
  // coming into the viewport so we can load the next products page if there is
  // one
  useViewportEntry(gridEndRef, handleGridScrolledToEnd);

  return (
    <>
      <div className="flex gap-6">
        <div className="min-w-64">
          <Filter
            applyFilter={handleApplyFilter}
            budget={budget}
            numSelected={selectedProductIds.length}
            selectedProductIds={selectedProductIds}
            products={products}
            baseSPAAssetsUrl={baseSPAAssetsUrl}
            handleRemoveProduct={handleRemoveProduct}
          />
        </div>
        {loading && queryParams.page === 1 ? (
          <div className="w-full h-full flex">
            <div className="m-auto w-fit">
              <Loader />
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-4">
            {products.map((p) => (
              <SelectionContainer
                key={`product-selection-${p.id}`}
                selected={selectedProductIds.includes(p.id)}
                onClick={() => onProductClick(p.id)}
              >
                <ProductCard
                  key={`product-${p.id}`}
                  image={p.images.length > 0 ? p.images[0].image : undefined}
                  total_cost={p.total_cost}
                  google_price={p.google_price}
                  brandImage={p.brand.logo_image}
                  name={p.name}
                  organization_price={p.calculated_price}
                />
              </SelectionContainer>
            ))}
            {!loading && <div ref={gridEndRef} className="w-[1px] h-[1px]" />}
          </div>
        )}
      </div>
      <select
        id={`id_${currentWizardStep}-${formId.toString()}-products`}
        name={`${currentWizardStep}-${formId.toString()}-products`}
        required
        multiple
        hidden
      >
        {selectedProductIds.map((selectedProduct) => (
          <option
            key={`selected-product-${selectedProduct}`}
            value={selectedProduct}
            selected
          >
            {selectedProduct}
          </option>
        ))}
      </select>
    </>
  );
};

export default ProductComponent;
