/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}',],
  theme: {
    extend: {
        width: {
          '17': '74px',
          '3/16': '18%'
        },
        height: {
          '6-1': '22px',
        },
        boxShadow: {
          't-lg': '0px 12px 24px -4px rgba(145, 158, 171, 0.12),0px 0px 2px 0px rgba(145, 158, 171, 0.2)',
          't-lg-1': '0px 12px 24px -4px rgba(145, 158, 171, 0.12), 0px 0px 2px 0px rgba(145, 158, 171, 0.2)',
        },
        colors: {
          primary: '#363839',
          'orange-111': 'rgba(250, 159, 86, 0.16)',
          'orange-112': 'rgba(224, 103, 5, 1)',
          'text-secondary': 'rgba(134, 135, 136, 1)',
          'text-primary': 'rgba(54, 56, 57, 1)',
          'border-color-1': 'var(--grey-8, rgba(189, 189, 189, 0.08))',
          'dj-admin-color-1': '#417690',
          'dj-admin-color-2': '#205067'
        },
        fontFamily: {
          assistant: 'Assistant'
        },
        fontSize: {
          'xs-1': '13px',
          'xs-2': '10px'
        },
        lineHeight: {
          '5-1': '18px',
          '5-2': '22px'
        },
        spacing:{
          '0-3': '3px',
          '3-1': '13px',
        },
    },
  },
  plugins: [],
};
