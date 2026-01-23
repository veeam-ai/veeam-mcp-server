const safeStringify = (obj: any): string => {
  try {
    return JSON.stringify(obj);
  } catch {
    return '';
  }
};

export default safeStringify;