'use client';

import { MutableRefObject, useEffect } from 'react';

const useViewportEntry = (
  ref: MutableRefObject<HTMLDivElement | null>,
  cb: () => void,
  observerOptions?: IntersectionObserverInit,
) => {
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      // if the element is intersecting (with the viewport) call the callback
      if (entry.isIntersecting) {
        cb();
      }
    }, observerOptions);

    const currentElement = ref.current;

    if (currentElement) {
      observer.observe(currentElement);
    }

    return () => observer.disconnect();
  }, [ref, cb, observerOptions]);

  return null;
};

export default useViewportEntry;
