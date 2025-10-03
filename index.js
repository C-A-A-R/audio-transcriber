require('dotenv').config();
const express = require('express');
const axios = require('axios');
const fs = require('fs');
const { v4: uuidv4 } = require('uuid');
const { execSync } = require('child_process');

const app = express();
app.use(express.json({ limit: '50mb' }));

app.post('/transcribe', async (req, res) => {
  const { audioUrl, callbackUrl } = req.body;
  const tempId = uuidv4();
  const encPath = `/tmp/${tempId}.enc`;
  const mp3Path = `/tmp/${tempId}.mp3`;

  try {
    // Descargar el archivo .enc
    const audioRes = await axios.get(audioUrl, { responseType: 'arraybuffer' });
    fs.writeFileSync(encPath, Buffer.from(audioRes.data));

    // Convertir a .mp3 usando ffmpeg
    execSync(`ffmpeg -y -i ${encPath} ${mp3Path}`);

    // Subir a AssemblyAI
    const uploadRes = await axios.post(
      'https://api.assemblyai.com/v2/upload',
      fs.createReadStream(mp3Path),
      {
        headers: { authorization: process.env.ASSEMBLYAI_API }
      }
    );

    const audioUploadUrl = uploadRes.data.upload_url;

    // Iniciar transcripción
    const transcriptRes = await axios.post(
      'https://api.assemblyai.com/v2/transcript',
      { audio_url: audioUploadUrl },
      {
        headers: { authorization: process.env.ASSEMBLYAI_API }
      }
    );

    const transcriptId = transcriptRes.data.id;
    const pollingUrl = `https://api.assemblyai.com/v2/transcript/${transcriptId}`;

    // Polling cada 5 segundos
    const poll = setInterval(async () => {
      const statusRes = await axios.get(pollingUrl, {
        headers: { authorization: process.env.ASSEMBLYAI_API }
      });

      if (statusRes.data.status === 'completed') {
        clearInterval(poll);
        await axios.post(callbackUrl, { transcript: statusRes.data.text });
        fs.unlinkSync(encPath);
        fs.unlinkSync(mp3Path);
      }

      if (statusRes.data.status === 'error') {
        clearInterval(poll);
        await axios.post(callbackUrl, { error: statusRes.data.error });
        fs.unlinkSync(encPath);
        fs.unlinkSync(mp3Path);
      }
    }, 5000);

    res.json({ message: 'Transcripción iniciada', transcriptId });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Error al procesar el audio' });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Servidor activo en puerto ${PORT}`));