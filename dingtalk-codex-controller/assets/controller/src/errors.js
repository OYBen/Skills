export class ControllerError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "ControllerError";
    this.code = code;
    this.details = details;
  }
}

export function publicError(error) {
  if (error instanceof ControllerError) {
    return { code: error.code, message: error.message };
  }
  return { code: "INTERNAL_ERROR", message: "Internal controller error" };
}
