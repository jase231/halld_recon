void fit_pi0(){
  TCanvas *c1=new TCanvas("c1","Two photon mass distributions",1920,960);
  c1->Divide(3,1);
  c1->cd(1);
  TF1 *f1=new TF1("f1","gaus(0)+expo(3)",0.09,0.17);
  f1->SetParameters(100,0.125,0.004,2,-10,0);
  TH1F *h1=(TH1F*)_file0->FindObjectAny("h_2gamma_ECAL_ECAL");
  h1->GetXaxis()->SetRangeUser(0.08,0.18);
  f1->SetParameter(0,h1->GetMaximum());
  h1->Fit("f1");
  c1->cd(2);
  TH1F *h2=(TH1F*)_file0->FindObjectAny("h_2gamma_FCAL_FCAL");
  h2->GetXaxis()->SetRangeUser(0.08,0.18);
  f1->SetParameter(3,2);
  f1->SetParameter(4,-10);
  f1->SetParameter(2,0.008);
  f1->SetParameter(1,0.135);
  f1->SetParameter(0,h2->GetMaximum());
  h2->Fit("f1");
  c1->cd(3);
  TH1F *h3=(TH1F*)_file0->FindObjectAny("h_2gamma_BCAL_BCAL");
  f1->SetParameter(1,0.135);
  f1->SetParameter(2,0.01);
  f1->SetParameter(3,2);
  f1->SetParameter(4,-10);
  f1->SetParameter(0,h3->GetMaximum());
  h3->GetXaxis()->SetRangeUser(0.08,0.18);
  h3->Fit("f1");
}
