type Props = {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
};

export default function ProductCard({ selected, onClick, children }: Props) {
  return (
    <div className="relative cursor-pointer" onClick={onClick}>
      {children}
      {selected && (
        <div className="absolute top-0 right-0">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            version="1.1"
            fill="green"
            width="100"
            height="100"
            transform="scale(0.5 0.5)"
          >
            <path d="M90.9,8.8c-4.4-3.3-10.7-2.4-14,2.1L35.8,66.3L23.1,49.2c-3.3-4.4-9.5-5.4-14-2.1C4.6,50.4,3.7,56.7,7,61.1l20.8,28  c1.9,2.6,4.8,4,8,4c3.2,0,6.2-1.5,8.1-4L93,22.9C96.3,18.4,95.4,12.1,90.9,8.8z" />
          </svg>
        </div>
      )}
    </div>
  );
}
