#!/usr/bin/env python3
"""Independent inverse, sign/orientation and counting-statistics negative controls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import check_realistic_motion as check
from summarize_realistic_motion import paired, summarize
gen=check.gen

class Realistic(unittest.TestCase):
    @staticmethod
    def translation_control(root, outside=False):
        r=gen.recipe(nx=128,ny=96,frames=5,control='translation')
        g=np.stack([-np.arange(5),2*np.arange(5)],axis=-1).astype(float)
        if outside: g[-1,0]-=200
        m=dict(global_=g.tolist(),coeff_x=[0.]*18,coeff_y=[0.]*18,local_enabled=False)
        m['global']=m.pop('global_')
        star=root/'movie.star'
        star.write_text('data_general\n_rlnImageSizeX 128\n_rlnImageSizeY 96\n_rlnImageSizeZ 5\n'
                        '_rlnMicrographOriginalPixelSize 0.885\n_rlnMicrographStartFrame 1\n'
                        '_rlnMicrographBinning 1\n_rlnMotionModelVersion 0\n'
                        'data_global_shift\nloop_\n_rlnMicrographFrameNumber #1\n'
                        '_rlnMicrographShiftX #2\n_rlnMicrographShiftY #3\n'+
                        ''.join(f'{f+1} {x} {y}\n' for f,(x,y) in enumerate(g)))
        check.validate_star_rows(star,r)
        return r,m,check.read_motion_star(star)

    def test_finite_outside_runtime_and_star_keep_metrics(self):
        with tempfile.TemporaryDirectory() as t:
            r,m,star=self.translation_control(Path(t),outside=True)
            before=json.dumps(m)
            result=check.evaluate(r,m,star)
            self.assertEqual(result['sampling_status'],'OUTSIDE_FIXED_ROI')
            self.assertEqual(result['field_distance_status'],'FAIL')
            self.assertEqual(result['role'],'characterization')
            self.assertEqual(result['lattice']['roi'],[32,63,32,95])
            for family in ['field','global_trajectory','border','serialized_field']:
                self.assertAlmostEqual(result[family]['px']['rms'],200/np.sqrt(5))
                self.assertAlmostEqual(result[family]['angstrom']['max'],200*.885)
                self.assertEqual(result[family]['per_frame_px'][0]['max'],0)
                self.assertEqual(result[family]['per_frame_px'][-1]['max'],200)
            self.assertEqual(result['local_component']['px']['max'],0)
            self.assertEqual(result['star_roundtrip_loss']['px']['max'],0)
            self.assertTrue(result['signal_transfer_status'].startswith('UNRUN:'))
            json.dumps(result,allow_nan=False)
            self.assertEqual(json.dumps(m),before)

    def test_finite_outside_cli_is_characterization_not_input_error(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); receipt=root/'RECEIPT.json'; runtime=root/'runtime.json'
            log=root/'movie.log'; report=root/'report.json'
            log.write_text('Global alignment:\n Iteration 5: RMSD = 1.0 px\nLocal alignments:\n')
            command=[sys.executable,str(Path(check.__file__)),'--receipt',str(receipt),
                     '--runtime',str(runtime),'--star',str(root/'movie.star'),
                     '--log',str(log),'--json',str(report)]
            for outside in [False,True]:
                r,m,_=self.translation_control(root,outside=outside)
                receipt.write_text(json.dumps(dict(schema=gen.SCHEMA,recipe=r)))
                runtime.write_text(json.dumps(m))
                proc=subprocess.run(command,capture_output=True,text=True)
                # This field-only characterization CLI retains exit 0; v2's
                # separate image-sampling CLI uses exit 1 for an outside ROI.
                self.assertEqual(proc.returncode,0,proc.stderr)
                result=json.loads(report.read_text())
                self.assertEqual(result['sampling_status'],'OUTSIDE_FIXED_ROI' if outside else 'VALID')
                self.assertEqual(result['field_distance_status'],'FAIL' if outside else 'PASS')
                self.assertIs(result['convergence']['global_converged'],False)
                self.assertEqual(len(result['identity']),4)
                self.assertNotIn('signal',result)  # no image metrics in this evaluator
            report.unlink()
            m['global'][-1][0]=float('nan'); runtime.write_text(json.dumps(m))
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertFalse(report.exists())

    def test_summary_counts_finite_outside_characterization(self):
        import summarize_realistic_motion as summary
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); r,good,_=self.translation_control(root)
            _,outside,_=self.translation_control(root,outside=True)
            for seed in range(10):
                name=f'dose1-s{seed:02d}'; fixture=root/'fixtures'/name
                fixture.mkdir(parents=True)
                (fixture/'RECEIPT.json').write_text(json.dumps(dict(recipe=r)))
                for arm in summary.ARMS:
                    model=outside if arm=='cpu-both' else good
                    metrics=check.evaluate(r,model)
                    metrics['star_roundtrip_loss']=check.errors(np.zeros((5,1,2)),np.zeros((5,1,2)),r['pixel_size'])
                    metrics['convergence']=dict(global_converged=False if arm=='cpu-both' else True,patches=[])
                    out=root/'results'/name/arm; out.mkdir(parents=True)
                    for filename,data in [('metrics.json',metrics),('runtime.json',model),('RUN.json',dict(exit=0))]:
                        (out/filename).write_text(json.dumps(data,allow_nan=False))
            # Complete synthetic consumer controls, not retained native records.
            with patch.object(summary,'CONDITIONS',['dose1']): result=summary.summarize(root)
            table={row['arm']:row for row in result['table']}
            self.assertEqual(table['cpu-both']['invalid_sampling'],10)
            self.assertEqual(table['cpu-both']['field_distance_failures'],10)
            self.assertEqual(table['cpu-both']['global_nonconverged'],10)
            self.assertAlmostEqual(table['cpu-both']['median_field_px']['rms'],200/np.sqrt(5))
            self.assertEqual(table['cpu-none']['invalid_sampling'],0)
            self.assertEqual(table['cpu-none']['field_distance_failures'],0)
            self.assertEqual(len(result['rows']),90)
            json.dumps(result,allow_nan=False)

    def test_native_convergence_beats_rounded_rmsd(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'movie.log'
            p.write_text('Global alignment:\n Iteration 2: RMSD = 0.50 px\n [CUDA Global Alignment] completed; converged=yes\nLocal alignments:\nPatch (1, 1):\n Iteration 2: RMSD = 0.50 px\n [CUDA Patch Alignment] completed; converged=yes\n')
            d=check.convergence(p)
            self.assertIs(d['global_converged'],True)
            self.assertIs(d['patches'][0]['converged'],True)
            p.write_text('Global alignment:\n Iteration 5: RMSD = 0.5 px\nLocal alignments:\n')
            self.assertIsNone(check.convergence(p)['global_converged'])

    def test_refuse_incomplete_census(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'incomplete census'):
                summarize(Path(t))

    def test_runtime_polynomial_nonsquare(self):
        r=gen.recipe(nx=256,ny=192,frames=40)
        x=np.array([0.,128.,255.]);y=np.array([12.,94.,191.])
        cx=np.zeros(18);cy=np.zeros(18);cx[8]=.0002;cy[16]=.001
        m={'global':np.zeros((40,2)).tolist(),'coeff_x':cx.tolist(),'coeff_y':cy.tolist()}
        result=check.runtime_field(m,r,x,y)
        for f in [0,1,39]:
            want=np.stack([.0002*f**3*(x/256-.5)**2,.001*f**2*(x/256-.5)*(y/192-.5)],axis=-1)
            np.testing.assert_allclose(result[f],want,atol=1e-14)

    def test_paired_seed_statistics(self):
        a=np.ones(10); good=paired(a,a*.8);bad=paired(a,a*1.2)
        self.assertEqual(good['wins'],10);self.assertEqual(good['losses'],0)
        self.assertEqual(good['interpretation'],'improves')
        self.assertEqual(bad['interpretation'],'harms')
        self.assertAlmostEqual(good['sign_test_two_sided_p'],2/1024)
        self.assertEqual(paired(a,a)['ties'],10)
        self.assertEqual(paired(a,a)['interpretation'],'neutral/mixed')

    def test_inverse_and_negation_mutant(self):
        x,y=np.meshgrid(np.linspace(0,127,17),np.linspace(0,95,19))
        for kind in ['inmodel','outmodel']:
            r=gen.recipe(nx=128,ny=96,frames=40,motion=kind)
            d=gen.displacement(r,39,x,y)
            qx,qy=gen.inverse(r,39,x+d[...,0],y+d[...,1])
            np.testing.assert_allclose(qx,x,atol=1e-8); np.testing.assert_allclose(qy,y,atol=1e-8)
            bad=gen.displacement(r,39,x-d[...,0],y-d[...,1])
            self.assertGreater(np.max(abs(bad-d)),.1)

    def test_analytic_translation_rows(self):
        r=gen.recipe(nx=128,ny=96,frames=5,control='translation')
        x=np.array([4.,77.]); y=np.array([20.,70.])
        qx,qy=gen.inverse(r,3,x,y)
        np.testing.assert_array_equal(qx,x-3); np.testing.assert_array_equal(qy,y+6)
        np.testing.assert_array_equal(-gen.displacement(r,3,x,y),[[-3,6],[-3,6]])
        # TIFF stores flipped rows; conjugating the transform flips y motion.
        flipped=gen.displacement(r,3,x,r['ny']-1-y)*[1,-1]
        self.assertFalse(np.array_equal(flipped,gen.displacement(r,3,x,y)))

    def test_truth_metrics_kill_sign_axis_units_time(self):
        r=gen.recipe(nx=128,ny=96,frames=5,control='translation')
        g=np.stack([-np.arange(5),2*np.arange(5)],axis=-1).astype(float)
        m={'global':g.tolist(),'coeff_x':[0.]*18,'coeff_y':[0.]*18,'local_enabled':False}
        self.assertLess(check.evaluate(r,m)['field']['px']['max'],1e-12)
        for bad in [-g,g[:,::-1],g*.885,np.roll(g,1,axis=0)]:
            m['global']=bad.tolist()
            self.assertEqual(check.evaluate(r,m)['field_distance_status'],'FAIL')

    def test_polynomial_representation(self):
        r=gen.recipe(nx=256,ny=192,frames=40)
        x,y=np.meshgrid(np.linspace(0,255,9),np.linspace(0,191,9)); x=x.ravel(); y=y.ravel()
        u,v=x/r['nx']-.5,y/r['ny']-.5
        a=np.stack([np.ones_like(u),u,u*u,v,v*v,u*v],axis=-1)
        for f in [1,8,39]:
            d=gen.displacement(r,f,x,y)
            fit=a@np.linalg.lstsq(a,d,rcond=None)[0]
            np.testing.assert_allclose(fit,d,atol=1e-12)
        r['motion']='outmodel'; d=gen.displacement(r,39,x,y)
        self.assertGreater(np.max(abs(a@np.linalg.lstsq(a,d,rcond=None)[0]-d)),.1)

    def test_oversampled_synthesis_closure(self):
        r=gen.recipe(nx=64,ny=48,frames=5,control='translation')
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'expect.npy'
            proof=gen.expected(r,p)
            self.assertLess(proof['forward_inverse_max_px'],1e-8)
            a=np.load(p)
            # Integer translation must address identical oversampled scene samples.
            np.testing.assert_allclose(a[3,8:38,8:50],a[0,14:44,5:47],atol=1e-7)
            self.assertGreater(float(a.std()),.02)

    def test_counting_receipt_and_affine_intensity(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); p=root/'expect.npy'
            r=gen.recipe(nx=128,ny=96,frames=5)
            np.save(p,np.ones((5,96,128),dtype='<f4'))
            p.with_suffix('.json').write_text(json.dumps(dict(recipe=r,proof={'expectation_sha256':gen.digest(p)})))
            a=gen.generate(r,p,root/'a')
            b=gen.generate(r|dict(pedestal=32.),p,root/'b')
            raw=lambda q:np.memmap(q,dtype='<f4',offset=1024,mode='r').reshape(5,96,128)
            x,y=raw(root/'a/movie.mrcs'),raw(root/'b/movie.mrcs')
            np.testing.assert_array_equal(y-x,np.full(x.shape,31.))
            gen.generate(r|dict(scale=.25),p,root/'scaled')
            z=raw(root/'scaled/movie.mrcs')
            np.testing.assert_array_equal((z-1)/.25,x-1)
            self.assertLess(abs(float(x.mean())-1),.02)
            self.assertLess(abs(float(x.var())-1),.03)
            with self.assertRaises(FileExistsError): gen.generate(r,p,root/'a')
            with self.assertRaises(ValueError): gen.generate(r|dict(motion='outmodel'),p,root/'wrong')
            p.write_bytes(b'corrupt')
            with self.assertRaises(ValueError): gen.generate(r,p,root/'corrupt')

if __name__=='__main__': unittest.main()
