export default {
  async fetch(request, env) {
	const url = new URL(request.url);

	// --- Temporary debug route ---
	if (request.method === 'GET' && url.pathname === '/debug') {
	  return new Response(JSON.stringify({
		pinata_api_key_exists: !!env.PINATA_API_KEY,
		pinata_api_key_value: env.PINATA_API_KEY,
		pinata_secret_key_exists: !!env.PINATA_SECRET_KEY,
		pinata_secret_key_value: env.PINATA_SECRET_KEY,
		engine_url: env.ENGINE_URL
	  }), {
		status: 200,
		headers: { 'Content-Type': 'application/json' }
	  });
	}
	// --- End debug route ---

	if (request.method !== 'POST' || url.pathname !== '/mint') {
	  return new Response('Not found', { status: 404 });
	}

	try {
	  const { to, metadata } = await request.json();
	  if (!to || !metadata) {
		return new Response('Missing "to" or "metadata"', { status: 400 });
	  }

	  // 1. Pinata upload
	  const pinata = await fetch('https://api.pinata.cloud/pinning/pinJSONToIPFS', {
		method: 'POST',
		headers: {
		  'Content-Type': 'application/json',
		  pinata_api_key: env.PINATA_API_KEY,
		  pinata_secret_api_key: env.PINATA_SECRET_KEY
		},
		body: JSON.stringify({
		  pinataContent: metadata,
		  pinataMetadata: { name: `NFT for ${to}` }
		})
	  });

	  if (!pinata.ok) {
		throw new Error(`Pinata upload failed: ${await pinata.text()}`);
	  }
	  const { IpfsHash } = await pinata.json();
	  const tokenURI = `ipfs://${IpfsHash}`;

	  // 2. Engine mint
	  const enginePayload = {
		chainId: parseInt(env.CHAIN_ID) || 8453,
		contractAddress: env.CONTRACT_ADDRESS,
		functionName: 'mintTo',
		args: [to, tokenURI]
	  };

	  const engine = await fetch(`${env.ENGINE_URL}/v1/write/contract`, {
		method: 'POST',
		headers: {
		  'Content-Type': 'application/json',
		  'x-secret-key': env.ENGINE_SECRET_KEY,
		  'x-backend-wallet-address': env.BACKEND_WALLET_ADDRESS
		},
		body: JSON.stringify(enginePayload)
	  });

	  if (!engine.ok) {
		throw new Error(`Engine mint failed: ${await engine.text()}`);
	  }
	  const mintResult = await engine.json();

	  return new Response(JSON.stringify({
		success: true,
		transactionHash: mintResult.result?.transactionHash,
		tokenURI,
		ipfsHash: IpfsHash
	  }), {
		status: 200,
		headers: { 'Content-Type': 'application/json' }
	  });

	} catch (error) {
	  return new Response(JSON.stringify({ error: error.message }), {
		status: 500,
		headers: { 'Content-Type': 'application/json' }
	  });
	}
  }
};
