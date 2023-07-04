import './App.css';
import { useState, useRef, useEffect } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Sphere, TrackballControls, useTexture } from '@react-three/drei';

import * as THREE from 'three';
import { ColmapCamera, ColmapPoint3D } from './types';
import { Points3D, CameraPrimitives, MovableLine } from './ThreeComponent';

const hostname = window.location.hostname;
const port = 5001;


function SceneApp() {
  // console.log(hostname);
  const [isLoaded, setIsLoaded] = useState(false);
  const [colmapCameras, setColmapCameras] = useState(null);
  const [colmapPoints, setColmapPoints] = useState(null);

  // Interactive
  const [hideCameras, setHideCameras] = useState(false);

  // 
  const [trackBallEnabled, setTrackBallEnabled] = useState(true)
  const handleSwitchControls = () => {
    setTrackBallEnabled(enabled => !enabled)
  }

  useEffect(() => {
    let subpath;
    subpath = 'colmap_projects/json_models/P02_01_skeletons.json';
    fetch(`http://${hostname}:${port}/model/${subpath}`)
    .then(response => response.json())
    .then(model => {
      const points = model.points.map(e => new ColmapPoint3D(e));
      setColmapPoints(points);

      let cameras = model.images.map(e => new ColmapCamera(e));
      setColmapCameras(cameras);

      setIsLoaded(true);
    });

    const handleKeyDown = (event) => {
      if (event.key === 's') {
        setTrackBallEnabled(enabled => !enabled)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, []);

  if (isLoaded === false) { return <div>Loading...</div> }

  return <>
    <div>
    <button onClick={() => setHideCameras(!hideCameras)}>Hide Cameras</button>
    <span>Num cameras: {`${colmapCameras.length}`}</span>
    </div>
      
    <button onClick={handleSwitchControls}>Switch Controls (S)</button>

    <div className='container'
      style={{ width: window.innerWidth, height: window.innerHeight }}>
      <Canvas dpr={[1, 2]}>
        <color args={[0x0000000]} attach="background" />
        <ambientLight />
        {/* <OrbitControls enableDamping={false} minDistance={0.5} maxDistance={100}/> */}
        <TrackballControls enabled={trackBallEnabled} enableDamping={false} minDistance={0.5} maxDistance={100}
          rotateSpeed={2.0}/>
        <axesHelper args={[1]} />

        <CameraPrimitives size={0.1} cameras={colmapCameras} hideCameras={hideCameras}/>
        <Points3D size={0.01} points={colmapPoints}/>
        <MovableLine control_enabled={!trackBallEnabled}/>
      </Canvas>
    </div>
  </>
}

const App = SceneApp;

export default App;
