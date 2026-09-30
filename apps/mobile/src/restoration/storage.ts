export interface CheckpointStorage {
  read(): Promise<string | null>;
  write(value: string): Promise<void>;
  remove(): Promise<void>;
}

export interface SecureKeyValue {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

const CHUNK_LENGTH = 500;
const MAX_CHUNKS = 128;
const MAX_LENGTH = CHUNK_LENGTH * MAX_CHUNKS;

type Bank = 0 | 1;
type Manifest = { version: 1; bank: Bank; chunks: number; length: number; checksum: string };

function checksum(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function parseManifest(raw: string): Manifest {
  let candidate: unknown;
  try {
    candidate = JSON.parse(raw);
  } catch {
    throw new Error('Stored workspace checkpoint manifest is malformed');
  }
  if (typeof candidate !== 'object' || candidate === null) {
    throw new Error('Stored workspace checkpoint manifest is malformed');
  }
  const value = candidate as Record<string, unknown>;
  const validBank = value.bank === 0 || value.bank === 1;
  const validChunks = Number.isInteger(value.chunks) && (value.chunks as number) >= 0
    && (value.chunks as number) <= MAX_CHUNKS;
  const validLength = Number.isInteger(value.length) && (value.length as number) >= 0
    && (value.length as number) <= MAX_LENGTH;
  if (value.version !== 1 || !validBank || !validChunks || !validLength
      || typeof value.checksum !== 'string' || !/^[0-9a-f]{8}$/.test(value.checksum)) {
    throw new Error('Stored workspace checkpoint manifest is malformed');
  }
  const minimumChunks = Math.ceil((value.length as number) / CHUNK_LENGTH);
  const maximumChunks = Math.ceil((value.length as number) / (CHUNK_LENGTH - 1));
  if ((value.chunks as number) < minimumChunks || (value.chunks as number) > maximumChunks) {
    throw new Error('Stored workspace checkpoint manifest is malformed');
  }
  return candidate as Manifest;
}

export function createCheckpointStorage(kv: SecureKeyValue, prefix: string): CheckpointStorage {
  const manifestKey = `${prefix}.manifest`;
  const chunkKey = (bank: Bank, index: number) => `${prefix}.bank.${bank}.${index}`;
  let queue: Promise<void> = Promise.resolve();

  function serialize<T>(operation: () => Promise<T>): Promise<T> {
    const result = queue.then(operation);
    queue = result.then(() => undefined, () => undefined);
    return result;
  }

  async function currentManifest(): Promise<Manifest | null> {
    const raw = await kv.get(manifestKey);
    return raw === null ? null : parseManifest(raw);
  }

  return {
    read: () => serialize(async () => {
      const manifest = await currentManifest();
      if (manifest === null) return null;
      const chunks: string[] = [];
      for (let index = 0; index < manifest.chunks; index += 1) {
        const chunk = await kv.get(chunkKey(manifest.bank, index));
        if (chunk === null) throw new Error('Stored workspace checkpoint is incomplete');
        if (chunk.length > CHUNK_LENGTH) throw new Error('Stored workspace checkpoint is incomplete');
        chunks.push(chunk);
      }
      const value = chunks.join('');
      if (value.length !== manifest.length || checksum(value) !== manifest.checksum) {
        throw new Error('Stored workspace checkpoint is incomplete');
      }
      return value;
    }),

    write: value => serialize(async () => {
      if (value.length > MAX_LENGTH) {
        throw new Error(`Workspace checkpoint exceeds the ${MAX_LENGTH} character limit`);
      }
      const committed = await currentManifest();
      const bank: Bank = committed?.bank === 0 ? 1 : 0;
      const chunks: string[] = [];
      for (let offset = 0; offset < value.length;) {
        let end = Math.min(offset + CHUNK_LENGTH, value.length);
        const splitsSurrogatePair = end < value.length
          && value.charCodeAt(end - 1) >= 0xd800 && value.charCodeAt(end - 1) <= 0xdbff
          && value.charCodeAt(end) >= 0xdc00 && value.charCodeAt(end) <= 0xdfff;
        if (splitsSurrogatePair) end -= 1;
        chunks.push(value.slice(offset, end));
        offset = end;
      }
      if (chunks.length > MAX_CHUNKS) {
        throw new Error(`Workspace checkpoint exceeds the ${MAX_CHUNKS} chunk limit`);
      }
      for (let index = 0; index < chunks.length; index += 1) {
        await kv.set(chunkKey(bank, index), chunks[index]!);
      }
      const manifest: Manifest = {
        version: 1,
        bank,
        chunks: chunks.length,
        length: value.length,
        checksum: checksum(value),
      };
      await kv.set(manifestKey, JSON.stringify(manifest));
    }),

    remove: () => serialize(async () => {
      // Remove the logical commit first. Any later cleanup failure leaves no readable checkpoint.
      await kv.remove(manifestKey);
      const removals: Promise<void>[] = [];
      for (const bank of [0, 1] as const) for (let index = 0; index < MAX_CHUNKS; index += 1) {
        removals.push(kv.remove(chunkKey(bank, index)));
      }
      const results = await Promise.allSettled(removals);
      if (results.some(result => result.status === 'rejected')) throw new Error('Workspace cleanup could not finish');
    }),
  };
}
