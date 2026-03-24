declare module "mammoth/mammoth.browser.js" {
  const mammoth: {
    convertToHtml(input: { arrayBuffer: ArrayBuffer }): Promise<{ value: string }>;
  };
  export default mammoth;
}
