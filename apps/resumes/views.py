from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.contrib import messages

from base.http import Http403
from base.utils import now_localized
from resumes.models import Resume
from resumes.forms import ResumeForm
from perms.object_perms import ObjectPermission
from perms.utils import update_perms_and_save, get_notice_recipients, is_admin, has_perm
from event_logs.models import EventLog
from meta.models import Meta as MetaTags
from meta.forms import MetaForm

try:
    from notification import models as notification
except:
    notification = None

def index(request, slug=None, template_name="resumes/view.html"):
    if not slug: return HttpResponseRedirect(reverse('resume.search'))
    resume = get_object_or_404(Resume, slug=slug)
    
    if has_perm(request.user,'resumes.view_resume',resume):
        log_defaults = {
            'event_id' : 355000,
            'event_data': '%s (%d) viewed by %s' % (resume._meta.object_name, resume.pk, request.user),
            'description': '%s viewed' % resume._meta.object_name,
            'user': request.user,
            'request': request,
            'instance': resume,
        }
        EventLog.objects.log(**log_defaults)
        return render_to_response(template_name, {'resume': resume}, 
            context_instance=RequestContext(request))
    else:
        raise Http403

def search(request, template_name="resumes/search.html"):
    query = request.GET.get('q', None)
    resumes = Resume.objects.search(query, user=request.user)
    resumes = resumes.order_by('-create_dt')

    log_defaults = {
        'event_id' : 354000,
        'event_data': '%s searched by %s' % ('Resume', request.user),
        'description': '%s searched' % 'Resume',
        'user': request.user,
        'request': request,
        'source': 'resumes'
    }
    EventLog.objects.log(**log_defaults)
    
    return render_to_response(template_name, {'resumes':resumes}, 
        context_instance=RequestContext(request))

def print_view(request, slug, template_name="resumes/print-view.html"):
    resume = get_object_or_404(Resume, slug=slug)    

    log_defaults = {
        'event_id' : 355001,
        'event_data': '%s (%d) viewed by %s' % (resume._meta.object_name, resume.pk, request.user),
        'description': '%s viewed - print view' % resume._meta.object_name,
        'user': request.user,
        'request': request,
        'instance': resume,
    }
    EventLog.objects.log(**log_defaults)
       
    if has_perm(request.user,'resumes.view_resume',resume):
        return render_to_response(template_name, {'resume': resume}, 
            context_instance=RequestContext(request))
    else:
        raise Http403

@login_required
def add(request, form_class=ResumeForm, template_name="resumes/add.html"):
    if request.method == "POST":
        form = form_class(request.POST, user=request.user)
        if form.is_valid():
            resume = form.save(commit=False)

            # set it to pending if the user is anonymous
            if not request.user.is_authenticated():
                resume.status = 0
                resume.status_detail = 'pending'

            # set up the expiration time based on requested duration
            now = now_localized()
            resume.expiration_dt = now + timedelta(days=resume.requested_duration)

            resume = update_perms_and_save(request, form, resume)

            log_defaults = {
                'event_id' : 351000,
                'event_data': '%s (%d) added by %s' % (resume._meta.object_name, resume.pk, request.user),
                'description': '%s added' % resume._meta.object_name,
                'user': request.user,
                'request': request,
                'instance': resume,
            }
            EventLog.objects.log(**log_defaults)

            if request.user.is_authenticated():
                messages.add_message(request, messages.INFO, 'Successfully added %s' % resume)

            # send notification to administrators
            recipients = get_notice_recipients('module', 'resumes', 'resumerecipients')
            if recipients:
                if notification:
                    extra_context = {
                        'object': resume,
                        'request': request,
                    }
                    notification.send_emails(recipients,'resume_added', extra_context)

            if not request.user.is_authenticated():
                return HttpResponseRedirect(reverse('resume.thank_you'))
            else:
                return HttpResponseRedirect(reverse('resume', args=[resume.slug]))
    else:
        form = form_class(user=request.user)

    return render_to_response(template_name, {'form':form},
        context_instance=RequestContext(request))

@login_required
def edit(request, id, form_class=ResumeForm, template_name="resumes/edit.html"):
    resume = get_object_or_404(Resume, pk=id)

    if has_perm(request.user,'resumes.change_resume',resume):    
        if request.method == "POST":
            form = form_class(request.POST, instance=resume, user=request.user)
            if form.is_valid():
                resume = form.save(commit=False)
                resume = update_perms_and_save(request, form, resume)

                log_defaults = {
                    'event_id' : 352000,
                    'event_data': '%s (%d) edited by %s' % (resume._meta.object_name, resume.pk, request.user),
                    'description': '%s edited' % resume._meta.object_name,
                    'user': request.user,
                    'request': request,
                    'instance': resume,
                }
                EventLog.objects.log(**log_defaults) 
                
                messages.add_message(request, messages.INFO, 'Successfully updated %s' % resume)
                                                              
                return HttpResponseRedirect(reverse('resume', args=[resume.slug]))             
        else:
            form = form_class(instance=resume, user=request.user)

        return render_to_response(template_name, {'resume': resume, 'form':form}, 
            context_instance=RequestContext(request))
    else:
        raise Http403

@login_required
def edit_meta(request, id, form_class=MetaForm, template_name="resumes/edit-meta.html"):

    # check permission
    resume = get_object_or_404(Resume, pk=id)
    if not has_perm(request.user,'resumes.change_resume',resume):
        raise Http403

    defaults = {
        'title': resume.get_title(),
        'description': resume.get_description(),
        'keywords': resume.get_keywords(),
        'canonical_url': resume.get_canonical_url(),
    }
    resume.meta = MetaTags(**defaults)


    if request.method == "POST":
        form = form_class(request.POST, instance=resume.meta)
        if form.is_valid():
            resume.meta = form.save() # save meta
            resume.save() # save relationship

            messages.add_message(request, messages.INFO, 'Successfully updated meta for %s' % resume)
            
            return HttpResponseRedirect(reverse('resume', args=[resume.slug]))
    else:
        form = form_class(instance=resume.meta)

    return render_to_response(template_name, {'resume': resume, 'form':form}, 
        context_instance=RequestContext(request))

@login_required
def delete(request, id, template_name="resumes/delete.html"):
    resume = get_object_or_404(Resume, pk=id)

    if has_perm(request.user,'resumes.delete_resume'):   
        if request.method == "POST":
            log_defaults = {
                'event_id' : 433000,
                'event_data': '%s (%d) deleted by %s' % (resume._meta.object_name, resume.pk, request.user),
                'description': '%s deleted' % resume._meta.object_name,
                'user': request.user,
                'request': request,
                'instance': resume,
            }
            
            EventLog.objects.log(**log_defaults)
            messages.add_message(request, messages.INFO, 'Successfully deleted %s' % resume)
            
            # send notification to administrators
            recipients = get_notice_recipients('module', 'resumes', 'resumerecipients')
            if recipients:
                if notification:
                    extra_context = {
                        'object': resume,
                        'request': request,
                    }
                    notification.send_emails(recipients,'resume_deleted', extra_context)
            
            resume.delete()
                
            return HttpResponseRedirect(reverse('resume.search'))
    
        return render_to_response(template_name, {'resume': resume}, 
            context_instance=RequestContext(request))
    else:
        raise Http403

@login_required
def pending(request, template_name="resumes/pending.html"):
    if not is_admin(request.user):
        raise Http403
    resumes = Resume.objects.filter(status=0, status_detail='pending')
    return render_to_response(template_name, {'resumes': resumes},
            context_instance=RequestContext(request))

@login_required
def approve(request, id, template_name="resumes/approve.html"):
    if not is_admin(request.user):
        raise Http403
    resume = get_object_or_404(Resume, pk=id)

    if request.method == "POST":
        resume.activation_dt = now_localized()
        resume.allow_anonymous_view = True
        resume.status = True
        resume.status_detail = 'active'

        if not resume.creator:
            resume.creator = request.user
            resume.creator_username = request.user.username

        if not resume.owner:
            resume.owner = request.user
            resume.owner_username = request.user.username

        resume.save()

        messages.add_message(request, messages.INFO, 'Successfully approved %s' % resume)

        return HttpResponseRedirect(reverse('resume', args=[resume.slug]))

    return render_to_response(template_name, {'resume': resume},
            context_instance=RequestContext(request))

def thank_you(request, template_name="resumes/thank-you.html"):
    return render_to_response(template_name, {}, context_instance=RequestContext(request))