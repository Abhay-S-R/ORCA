/** @type {import('jest').Config} */
const config = {
  // Use ts-jest for TypeScript support
  preset: "ts-jest",

  // Test environment (jsdom for React components)
  testEnvironment: "jsdom",

  // Root directory for tests
  roots: ["<rootDir>/app"],

  // Test file patterns
  testMatch: ["**/__tests__/**/*.{ts,tsx}", "**/*.{spec,test}.{ts,tsx}"],

  // Module name mapper for path aliases
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/app/$1",
    // Mock CSS and asset imports
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
    "\\.(jpg|jpeg|png|gif|svg)$": "<rootDir>/__mocks__/fileMock.js",
  },

  // Setup files
  setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],

  // Transform files with ts-jest
  transform: {
    "^.+\\.tsx?$": [
      "ts-jest",
      {
        tsconfig: {
          jsx: "react",
          esModuleInterop: true,
          allowSyntheticDefaultImports: true,
        },
      },
    ],
  },

  // Coverage configuration
  collectCoverageFrom: [
    "app/**/*.{ts,tsx}",
    "!app/**/*.d.ts",
    "!app/**/*.stories.{ts,tsx}",
    "!app/**/index.{ts,tsx}",
  ],

  // Ignore patterns
  testPathIgnorePatterns: ["/node_modules/", "/.next/"],

  // Module file extensions
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json"],
};

module.exports = config;
