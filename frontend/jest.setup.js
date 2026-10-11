/* eslint-disable @typescript-eslint/no-require-imports */
// Jest setup file for configuring test environment
require("@testing-library/jest-dom");

// Mock framer-motion to avoid animation issues in tests
jest.mock("framer-motion", () => {
  const React = require("react");
  return {
    motion: {
      div: ({ children, ...props }) =>
        React.createElement("div", props, children),
      button: ({ children, ...props }) =>
        React.createElement("button", props, children),
      li: ({ children, ...props }) =>
        React.createElement("li", props, children),
      span: ({ children, ...props }) =>
        React.createElement("span", props, children),
    },
    AnimatePresence: ({ children }) => children,
    useReducedMotion: () => false,
  };
});

// Mock window.matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: jest.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});
