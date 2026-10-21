#!/usr/bin/env python3
"""Independent inverse, sign/orientation and counting-statistics negative controls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
import check_realistic_motion as check
from summarize_realistic_motion import paired
gen=check.gen

class Realistic(unittest.TestCase):
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
