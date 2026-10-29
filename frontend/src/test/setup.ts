import "@testing-library/jest-dom";

// Mock URL.createObjectURL & URL.revokeObjectURL in JSDOM
if (typeof window !== "undefined") {
  if (!window.URL.createObjectURL) {
    window.URL.createObjectURL = () => "blob:http://localhost/mock-blob-uuid";
  }
  if (!window.URL.revokeObjectURL) {
    window.URL.revokeObjectURL = () => {};
  }
}
