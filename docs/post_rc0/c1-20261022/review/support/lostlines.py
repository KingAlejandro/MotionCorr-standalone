import subprocess,sys,collections,json
M="3691374061f782bc84531fd1c79d017ddcb5a7c2"; F="e77a51a220cb0d91f4ac3c7fac211876d0c6833f"
heads=[("267","6695241523d7285d4f0480abf1c4a2c6423c3617"),("269","1b29b7f9eea1976a0b7a9e2ef5f9ca00477324b1"),("272","1f0a58bf6e0639d8b62f74da52f250cc664c0b30"),("254","b7f4517669b3eae2f7d83f767b1ef6c7bf3681ad"),("260","2b23fd3cebcab116240ece1566fb7f3510423a25"),("270","09ee7cb0a48a3f9bc0301239af475134cb78cd6d"),("252","ad0c61a369499b9d1444b804cd9850a167fea646"),("251","1dbdd47e875422655ad54bd453be01addb2fef5a"),("244","1b8239b1518e882a26fc77f061d48c0e4afb3632"),("248","855b134e6503096c84f3ac11308f5fdb4a70e1b0"),("249","5791f69e775f8151b953e159f45ba8b20a33bf12"),("245","b8b8adbf12978ef580b227eac512da938a0f8225"),("242","430699df47b76568555ce043b4d5d3279ee6fd56"),("241","6c72a87b464486175bd91175b2b5c304da54fabe")]
def g(*a):
    return subprocess.run(["git",*a],capture_output=True,text=True,errors="replace").stdout
out={}
for n,h in heads:
    mb=g("merge-base",M,h).strip()
    files=g("diff","--name-only",mb,h).split()
    res={}
    for f in files:
        # added lines (multiset) of PR relative to merge-base
        d=g("diff","-U0",mb,h,"--",f)
        add=collections.Counter(l[1:] for l in d.splitlines() if l.startswith("+") and not l.startswith("+++"))
        rem=collections.Counter(l[1:] for l in d.splitlines() if l.startswith("-") and not l.startswith("---"))
        fin=g("show",f"{F}:{f}")
        finc=collections.Counter(fin.splitlines())
        lost=sum(max(0,c-finc.get(l,0)) for l,c in add.items() if l.strip())
        # removed lines by PR that still exist in final (removal lost?)
        kept_rem=sum(max(0,min(c,finc.get(l,0))) for l,c in rem.items() if l.strip() and l not in add)
        if lost or kept_rem or not fin:
            res[f]={"lost_added_lines":lost,"pr_removed_but_present":kept_rem,"missing_in_final":not fin}
    out[n]={"mergebase":mb[:8],"nfiles":len(files),"issues":res}
json.dump(out,open(sys.argv[1],"w"),indent=1)
for n,v in out.items(): print(n,v["mergebase"],v["nfiles"],v["issues"])
